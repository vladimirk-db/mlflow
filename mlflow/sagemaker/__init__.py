from __future__ import print_function

import os
from subprocess import Popen, PIPE, STDOUT
from urlparse import urlparse
import tarfile

import boto3

import mlflow
from mlflow import pyfunc
from mlflow.models import Model
from mlflow.tracking import _get_model_log_dir
from mlflow.utils.logging_utils import eprint
from mlflow.utils.file_utils import TempDir, _copy_project

DEFAULT_IMAGE_NAME = "mlflow-pyfunc"

PREBUILT_IMAGE_URLS = {
    "us-west-2": "XXXXXXX.dkr.ecr.us-west-2.amazonaws.com/mlflow-pyfunc",
}

DEPLOYMENT_MODE_ADD = "add"
DEPLOYMENT_MODE_REPLACE = "replace"
DEPLOYMENT_MODE_CREATE = "create"

DEPLOYMENT_MODES = [
    DEPLOYMENT_MODE_CREATE,
    DEPLOYMENT_MODE_ADD,
    DEPLOYMENT_MODE_REPLACE
]

def _get_prebuilt_image_url(region):
    if region not in PREBUILT_IMAGE_URLS:
        raise ValueError(
            "Prebuilt images are not available in region {region}. ".format(region=region) +
            "Please specify a valid region or an image_url in the desired region. " +
            "Valid regions are: {regions}".format(regions=", ".join(PREBUILT_IMAGE_URLS.keys())))
    return (PREBUILT_IMAGE_URLS[region] + ":{version}").format(version=mlflow.version.VERSION)

DEFAULT_BUCKET_NAME_PREFIX = "mlflow-sagemaker"

_DOCKERFILE_TEMPLATE = """
# Build an image that can serve pyfunc model in SageMaker
FROM ubuntu:16.04

RUN apt-get -y update && apt-get install -y --no-install-recommends \
         wget \
         curl \
         nginx \
         ca-certificates \
         bzip2 \
         build-essential \
         cmake \
         git-core \
    && rm -rf /var/lib/apt/lists/*

# Download and setup miniconda
RUN curl https://repo.continuum.io/miniconda/Miniconda3-latest-Linux-x86_64.sh >> miniconda.sh
RUN bash ./miniconda.sh -b -p /miniconda; rm ./miniconda.sh;
ENV PATH="/miniconda/bin:${PATH}"

RUN conda install -c anaconda gunicorn;\
    conda install -c anaconda gevent;\

%s

# Set up the program in the image
WORKDIR /opt/mlflow

# start mlflow scoring
ENTRYPOINT ["python", "-c", "import sys; from mlflow.sagemaker import container as C; \
C._init(sys.argv[1])"]
"""


def _docker_ignore(mlflow_root):
    docker_ignore = os.path.join(mlflow_root, '.dockerignore')

    def strip_slash(x):
        if x.startswith("/"):
            x = x[1:]
        if x.endswith('/'):
            x = x[:-1]
        return x

    if os.path.exists(docker_ignore):
        with open(docker_ignore, "r") as f:
            patterns = [x.strip() for x in f.readlines()]
            patterns = [strip_slash(x) for x in patterns if not x.startswith("#")]

    def ignore(_, names):
        import fnmatch
        res = set()
        for p in patterns:
            res.update(set(fnmatch.filter(names, p)))
        return list(res)

    return ignore


def build_image(name=DEFAULT_IMAGE_NAME, mlflow_home=None):
    """
    This function builds an MLflow Docker image.
    The image is built locally and it requires Docker to run.

    :param name: image name
    """
    with TempDir() as tmp:
        install_mlflow = "RUN pip install mlflow=={version}".format(version=mlflow.version.VERSION)
        cwd = tmp.path()
        if mlflow_home:
            mlflow_dir = _copy_project(src_path=mlflow_home, dst_path=tmp.path())
            install_mlflow = "COPY {mlflow_dir} /opt/mlflow\n RUN pip install /opt/mlflow\n"
            install_mlflow = install_mlflow.format(mlflow_dir=mlflow_dir)

        with open(os.path.join(cwd, "Dockerfile"), "w") as f:
            f.write(_DOCKERFILE_TEMPLATE % install_mlflow)
        eprint("building docker image")
        os.system('find {cwd}/'.format(cwd=cwd))
        proc = Popen(["docker", "build", "-t", name, "-f", "Dockerfile", "."],
                     cwd=cwd,
                     stdout=PIPE,
                     stderr=STDOUT,
                     universal_newlines=True)
        for x in iter(proc.stdout.readline, ""):
            eprint(x, end='')


_full_template = "{account}.dkr.ecr.{region}.amazonaws.com/{image}:{version}"


def push_image_to_ecr(image=DEFAULT_IMAGE_NAME):
    """
    Push local Docker image to ECR.

    The image is pushed under current active aws account and to current active AWS region.

    :param image: image name
    """
    eprint("Pushing image to ECR")
    client = boto3.client("sts")
    caller_id = client.get_caller_identity()
    account = caller_id['Account']
    my_session = boto3.session.Session()
    region = my_session.region_name or "us-west-2"
    fullname = _full_template.format(account=account, region=region, image=image, version=mlflow.version.VERSION)
    eprint("Pushing docker image {image} to {repo}".format(image=image, repo=fullname))
    ecr_client = boto3.client('ecr')
    if not ecr_client.describe_repositories(repositoryNames=[image])['repositories']:
        ecr_client.create_repository(repositoryName=image)
    # TODO: it would be nice to translate the docker login, tag and push to python api.
    # x = ecr_client.get_authorization_token()['authorizationData'][0]
    # docker_login_cmd = "docker login -u AWS -p {token} {url}".format(token=x['authorizationToken']
    #                                                                ,url=x['proxyEndpoint'])
    docker_login_cmd = "$(aws ecr get-login --no-include-email)"
    docker_tag_cmd = "docker tag {image} {fullname}".format(image=image, fullname=fullname)
    docker_push_cmd = "docker push {}".format(fullname)
    cmd = ";\n".join([docker_login_cmd, docker_tag_cmd, docker_push_cmd])
    os.system(cmd)


def deploy(app_name, model_path, execution_role_arn=None, bucket=None, run_id=None,
           image_url=None, region_name="us-west-2", mode=DEPLOYMENT_MODE_CREATE):
    """
    Deploy model on SageMaker.
    Current active AWS account needs to have correct permissions setup.

    :param app_name: Name of the deployed application.
    :param path: Path to the model.
                 Either local if no run_id or MLflow-relative if run_id is specified)
    :param execution_role_arn: Amazon execution role with sagemaker rights. defaults
                               to the currently-assumed role.
    :param bucket: S3 bucket where model artifacts will be stored. defaults to a
                   SageMaker-compatible bucket name.
    :param run_id: MLflow run id.
    :param image: name of the Docker image to be used. if not specified, uses a 
                  publicly-available pre-built image.
    :param region_name: Name of the AWS region to which to deploy the application.
    :param mode: The mode in which to deploy the application. Must be one of the following:
                 `create`: Creates an application with the specified name and model. 
                           This will fail if an application of the same name already exists.
                 `replace`: Creates an application with the specified name and model.
                            This will replace any pre-existing applications of the same name.
                 `add`: Adds the specified model to a pre-existing application with the specified 
                        name, if one exists. If the application does not exist, a new application
                        will be created with the specified name and model.
    """
    assert mode in DEPLOYMENT_MODES, "`mode` must be one of: {mds}".format(mds=",".join(DEPLOYMENT_MODES))

    if not image_url:
        image_url = _get_prebuilt_image_url(region_name)

    if not execution_role_arn:
        execution_role_arn = _get_assumed_role_arn()

    if not bucket:
        eprint("No model data bucket specified, using the default bucket") 
        bucket = _get_default_s3_bucket(region_name)

    prefix = model_path
    if run_id:
        model_path = _get_model_log_dir(model_path, run_id)
        prefix = os.path.join(run_id, prefix)
    run_id = _check_compatible(model_path)

    model_s3_path = _upload_s3(local_model_path=model_path, bucket=bucket, prefix=prefix)
    _deploy(role=execution_role_arn,
            image_url=image_url,
            app_name=app_name,
            model_s3_path=model_s3_path,
            run_id=run_id,
            region_name=region_name,
            model=mode)


def delete(app_name, region_name="us-west-2"):
    """
    :param app_name: Name of the deployed application.
    :param region_name: Name of the AWS region in which the application is deployed.
    """
    s3_client = boto3.client('s3', region_name=region_name)
    sage_client = boto3.client('sagemaker', region_name=region_name)

    endpoint_info = sage_client.describe_endpoint(EndpointName=app_name)
    config_name = endpoint_info["EndpointConfigName"]
    config_info = sage_client.describe_endpoint_config(EndpointConfigName=config_name)

    for pv in config_info["ProductionVariants"]:
        model_name = pv["ModelName"]
        model_info = sage_client.describe_model(ModelName=model_name)
        model_data_url = model_info["PrimaryContainer"]["ModelDataUrl"]
        parsed_data_url = urlparse(model_data_url)
        bucket_data_path = parsed_data_url.path.split("/")
        bucket_name = bucket_data_path[1]
        bucket_key = "/".join(bucket_data_path[2:])

        s3_client.delete_object(Bucket=bucket_name,
                                Key=bucket_key)
        sage_client.delete_model(ModelName=model_name)

    sage_client.delete_endpoint_config(EndpointConfigName=config_name)
    sage_client.delete_endpoint(EndpointName=app_name)


def run_local(model_path, run_id=None, port=5000, image=DEFAULT_IMAGE_NAME):
    """
    Serve model locally in a SageMaker compatible Docker container.
    :param model_path:  Path to the model.
    Either local if no run_id or MLflow-relative if run_id is specified)
    :param run_id: MLflow RUN-ID.
    :param port: local port
    :param image: name of the Docker image to be used.
    """
    if run_id:
        model_path = _get_model_log_dir(model_path, run_id)
    _check_compatible(model_path)
    model_path = os.path.abspath(model_path)
    eprint("launching docker image with path {}".format(model_path))
    cmd = ["docker", "run", "-v", "{}:/opt/ml/model/".format(model_path), "-p", "%d:8080" % port,
           "--rm", image, "serve"]
    eprint('executing', ' '.join(cmd))
    proc = Popen(cmd, stdout=PIPE, stderr=STDOUT, universal_newlines=True)

    def _sigterm_handler(*_):
        eprint("received termination signal => killing docker process")
        proc.send_signal(signal.SIGINT)

    import signal
    signal.signal(signal.SIGTERM, _sigterm_handler)
    for x in iter(proc.stdout.readline, ""):
        eprint(x, end='')


def _check_compatible(path):
    """
    Check that we can handle this model and rasie exception if we can not.
    :return: RUN_ID if it exists or None
    """
    path = os.path.abspath(path)
    model = Model.load(os.path.join(path, "MLmodel"))
    if pyfunc.FLAVOR_NAME not in model.flavors:
        raise Exception("Currenlty only supports pyfunc format.")
    return model.run_id if hasattr(model, "run_id") else None


def _get_account_id():
    sess = boto3.Session()
    sts_client = sess.client("sts")
    identity_info = sts_client.get_caller_identity()
    account_id = identity_info["Account"]
    return account_id 


def _get_assumed_role_arn():
    """
    :return: ARN of the user's current IAM role 
    """
    sess = boto3.Session()
    sts_client = sess.client("sts")
    identity_info = sts_client.get_caller_identity()
    sts_arn = identity_info["Arn"]
    role_name = sts_arn.split("/")[1]
    iam_client = sess.client("iam")
    role_response = iam_client.get_role(RoleName=role_name)
    return role_response["Role"]["Arn"]


def _get_default_s3_bucket(region_name):
    # create bucket if it does not exist
    sess = boto3.Session()
    account_id = _get_account_id()
    bucket_name = "{pfx}-{rn}-{aid}".format(pfx=DEFAULT_BUCKET_NAME_PREFIX, rn=region_name, aid=account_id)
    s3 = sess.client('s3')
    response = s3.list_buckets()
    buckets = [b['Name'] for b in response["Buckets"]]
    if not bucket_name in buckets:
        eprint("Default bucket `%s` not found. Creating..." % bucket_name)
        response = s3.create_bucket(
            ACL='bucket-owner-full-control',
            Bucket=bucket_name,
            CreateBucketConfiguration={
                'LocationConstraint': region_name, 
            },
        )
        eprint(response)
    else:
        eprint("Default bucket `%s` already exists. Skipping creation." % bucket_name)
    return bucket_name


def _make_tarfile(output_filename, source_dir):
    """
    create a tar.gz from a directory.
    """
    with tarfile.open(output_filename, "w:gz") as tar:
        for f in os.listdir(source_dir):
            tar.add(os.path.join(source_dir, f), arcname=f)


def _upload_s3(local_model_path, bucket, prefix):
    """
    Upload dir to S3 as .tar.gz.
    :param local_model_path: local path to a dir.
    :param bucket: S3 bucket where to store the data.
    :param prefix: path within the bucket.
    :return: s3 path of the uploaded artifact
    """
    sess = boto3.Session()
    with TempDir() as tmp:
        model_data_file = tmp.path("model.tar.gz")
        _make_tarfile(model_data_file, local_model_path)
        s3 = boto3.client('s3')
        with open(model_data_file, 'rb') as fobj:
            key = os.path.join(prefix, 'model.tar.gz')
            obj = sess.resource('s3').Bucket(bucket).Object(key)
            obj.upload_fileobj(fobj)
            response = s3.put_object_tagging(
                Bucket=bucket,
                Key=key,
                Tagging={'TagSet': [{'Key': 'SageMaker', 'Value': 'true'}, ]}
            )
            eprint('tag response', response)
            return '{}/{}/{}'.format(s3.meta.endpoint_url, bucket, key)


def _deploy(role, image_url, app_name, model_s3_path, run_id, region_name, mode):
    """
    Deploy model on sagemaker.
    :param role: SageMaker execution ARN role
    :param image_url: URL of the ECR-hosted docker image the model is being deployed into
    :param app_name: Name of the deployed app
    :param model_s3_path: s3 path where we stored the model artifacts
    :param run_id: RunId that generated this model
    :param mode: The mode in which to deploy the application.
    """
    sage_client = boto3.client('sagemaker', region_name=region_name)

    deployed_endpoints = sage_client.list_endpoints()["Endpoints"]
    deployed_endpoints = [endp["EndpointName"] for enp in deployed_endpoints]

    endpoint_exists = (app_name in deployed_endpoints)
    if endpoint_exists and mode == DEPLOYMENT_MODE_CREATE:
        raise Exception("You are attempting to deploy application with name: {an} in `create` mode. However, an application with the same name"
                        " already exists. If you want to update this application, deploy in `{madd}` or `{mrep}` mode".format(madd=DEPLOYMENT_MODE_ADD,
                                                                                                                              mrep=DEPLOYMENT_MODE_REPLACE))
    
    elif endpoint_exists:
        # Update the endpoint according to the deployment mode specified
        # by the `mode` argument
        endpoint_info = sage_client.describe_endpoint(app_name)
        deployed_config_name = endpoint_info["EndpointConfigName"]
        deployed_config = sage_client.describe_endpoint_config(EndpointConfigName=config_name)
        deployed_production_variants = deployed_config["ProductionVariants"]
        latest_model_id = max([_get_model_id(pv["ModelName"]) for pv in deployed_production_variants])
        
        model_id = latest_model_id + 1
        model_name = _create_model_name(app_name, new_model_id)
        model_weight = 1 if (mode == DEPLOYMENT_MODE_REPLACE) else 0

        model_response = sage_client.create_model(
            ModelName=model_name,
            PrimaryContainer={
                'ContainerHostname': 'mlflow-serve-%s' % model_name,
                'Image': image_url,
                'ModelDataUrl': model_s3_path,
                'Environment': {},
            },
            ExecutionRoleArn=role,
            Tags=[{'Key': 'run_id', 'Value': str(run_id)}, ],
        )
        eprint("model_arn: %s" % model_response["ModelArn"])


        if mode == DEPLOYMENT_MODE_ADD:
            model_weight = 0
            production_variants = deployed_production_variants
        elif mode == DEPLOYMENT_MODE_REPLACE:
            model_weight = 1
            production_variants = [] 
        else:
            raise Exception("Unrecognized mode: `{md}` for deployment to pre-existing application".format(md=mode))

        new_production_variant = {
                                    'VariantName': 'model1',
                                    'ModelName': new_model_name,  # is this the unique identifier for Model?
                                    'InitialInstanceCount': 1,
                                    'InstanceType': 'ml.m4.xlarge',
                                    'InitialVariantWeight': model_weight 
                                 }

        production_variants.append(new_production_variant)

    else:
        # Create a new endpoint
        model_name = _create_model_name(app_name, model_id=0)

        model_response = sage_client.create_model(
            ModelName=model_name,
            PrimaryContainer={
                'ContainerHostname': 'mlflow-serve-%s' % model_name,
                'Image': image_url,
                'ModelDataUrl': model_s3_path,
                'Environment': {},
            },
            ExecutionRoleArn=role,
            Tags=[{'Key': 'run_id', 'Value': str(run_id)}, ],
        )
        eprint("model_arn: %s" % model_response["ModelArn"])

        production_variant = {
                                'VariantName': 'model1',
                                'ModelName': model_name,  # is this the unique identifier for Model?
                                'InitialInstanceCount': 1,
                                'InstanceType': 'ml.m4.xlarge',
                                'InitialVariantWeight': 1 
                             }
        endpoint_config_response = _create_endpoint_config(app_name=app_name,
                                                           production_variants=[production_variant])
        eprint("endpoint_config_arn: %s" % endpoint_config_response["EndpointConfigArn"])
        endpoint_response = sage_client.create_endpoint(
            EndpointName=app_name,
            EndpointConfigName=config_name,
            Tags=[],
        )
        eprint("endpoint_arn: %s" % endpoint_response["EndpointArn"])


def _get_model_id(model_name):
    return int(model_name.split("-")[-1])

def _create_model_name(app_name, model_id):
    return "{an}-model-{mid}".format(an=app_name, mid=model_id)

def _create_sagemaker_endpoint():
    pass

def _update_sagemaker_endpoint(mode):
    pass

def _create_endpoint_config(app_name, production_variants):
    endpoint_config_response = sage_client.create_endpoint_config(
        EndpointConfigName=config_name,
        ProductionVariants=production_variants,
        Tags=[
            {
                'Key': 'app_name',
                'Value': app_name,
            },
        ],
    )
    return endpoint_config_response
