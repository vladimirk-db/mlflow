import os
import yaml
from subprocess import Popen 

import mlflow
from mlflow.tracking.utils import _get_model_log_dir
from mlflow.utils.file_utils import TempDir, _copy_file_or_tree 
from mlflow.utils.docker import get_template, build_image, push_image
from mlflow.utils.docker import push_image as push_docker_image

MODEL_SERVER_INTERNAL_PORT = 8080
DEFAULT_SERVICE_PORT = 5001

SERVER_CONFIG_SUBPATH = "server_config.yaml"

DEPLOYMENT_CONFIG_TEMPLATE = """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {model_name} 
  labels:
    app: {model_name} 
spec:
  replicas: 1 
  selector:
    matchLabels:
      app: {model_name} 
  template:
    metadata:
      labels:
        app: {model_name} 
    spec:
      containers:
      - name: {model_name}
        image: {image_uri} 
        args: ["serve"]
        ports:
        - containerPort: {internal_port} 
"""

SERVICE_CONFIG_TEMPLATE = """\
apiVersion: v1
kind: Service
metadata:
  name: {model_name}-server
spec:
  type: NodePort
  selector:
    app: {model_name} 
  ports:
  - name: {model_name}-server-port
    protocol: TCP
    port: {service_port} 
    targetPort: {internal_port} 
"""


class ModelServerConfig:

    def __init__(self, deployment_config_subpath, service_config_subpath):
        self.deployment_config_subpath = deployment_config_subpath
        self.service_config_subpath = service_config_subpath

        
    def to_yaml(self, stream=None):
        return yaml.safe_dump(self.__dict__, stream=stream, default_flow_style=False)
    

    def save(self, path):
        with open(path, "w") as f:
            self.to_yaml(stream=f)


    @classmethod
    def load(cls, path):
        with open(path, "r") as f:
            return cls(**yaml.safe_load(f.read()))


def run_model_server(server_path, num_replicas=1):
    """
    :param root_server_path: The path to the model server directory containing kubernetes 
                             deployment and service configurations, generated by
                             `mlflow.kubernetes.build_model_server`.
    """
    model_server_config = ModelServerConfig.load(os.path.join(server_path, SERVER_CONFIG_SUBPATH))
    deployment_config_path = os.path.join(server_path, model_server_config.deployment_config_subpath)
    service_config_path = os.path.join(server_path, model_server_config.service_config_subpath)

    base_cmd = "kubectl create -f {config_path}"
    deployment_cmd = base_cmd.format(config_path=deployment_config_path)
    service_cmd = base_cmd.format(config_path=service_config_path)

    print(deployment_cmd)
    deployment_proc = Popen(deployment_cmd.split(" "))
    deployment_proc.wait()

    print(service_cmd)
    service_proc = Popen(service_cmd.split(" "))
    service_proc.wait()

    deployment_config = _load_kubernetes_config(config_path=deployment_config_path)
    deployment_name = deployment_config["metadata"]["name"]
    autoscale_cmd = "kubectl scale deployment {deployment_name} --replicas={num_replicas}".format(
            deployment_name=deployment_name, num_replicas=num_replicas)
    print(autoscale_cmd)
    autoscale_proc = Popen(autoscale_cmd.split(" "))
    autoscale_proc.wait()


def build_model_server(model_path, run_id=None, model_name=None, pyfunc_image_uri=None, 
                       mlflow_home=None, target_registry_uri=None, push_image=False, 
                       image_pull_secret=None, port=None, output_directory=None):
    """
    :param model_path: The path to the Mlflow model for which to build a server.
                       If `run_id` is not `None`, this should be an absolute path. Otherwise,
                       it should be a run-relative path.
    :param run_id: The run id of the Mlflow model for which to build a server.
    :param model_name: The name of the model; this will be used for naming within the 
                       Kubernetes deployment and service configurations. If `None`,
                       a name will be created using the specified model path and run id.
    :param pyfunc_image_uri: URI of an `mlflow-pyfunc` base Docker image from which the model server 
                             Docker image will be built. If `None`, the base image will be
                             built from scratch.
    :param mlflow_home: Path to the Mlflow root directory. This will only be used if the container
                        base image is being built from scratch (if `pyfunc_image_uri` is `None`).
                        If `mlflow_home` is `None`, the base image will install Mlflow from pip
                        during the build. Otherwise, it will install Mlflow from the specified
                        directory.
    :param target_registry_uri: The URI of the docker registry that Kubernetes will use to
                                pull the model server Docker image. If `None`, the default
                                docker registry (docker.io) will be used. Otherwise, the model 
                                server image will be tagged using the specified registry uri.
    :param push_image: If `True`, the model server Docker image will be pushed to the registry
                       specified by `target_registry_uri` (or docker.io if `target_registry_uri` is
                       `None`). If `False`, the model server Docker image will not be
                       pushed to a registry.
    :param image_pull_secret: The name of a Kubernetes secret that will be used to pull images
                              from the Docker registry specified by `target_registry_uri`.
    :param port: The cluster node port on which to expose the Kubernetes service for model 
                 serving. This value will be used for the `port` field of the Kubernetes
                 service spec (see mlflow.kubernetes.SERVICE_CONFIG_TEMPLATE for reference).
                 If `None`, the port defined by `mlflow.kubernetes.DEFAULT_SERVICE_PORT`
                 will be used.
    :param output_directory: The directory to which to write configuration files for the model 
                             model server. If `None`, the working directory from which this function 
                             was invoked will be used.
    """
    with TempDir() as tmp:
        cwd = tmp.path()
        dockerfile_template = _get_image_template(image_resources_path=cwd, 
                model_path=model_path, run_id=run_id, pyfunc_uri=pyfunc_image_uri, 
                mlflow_home=mlflow_home)

        template_path = os.path.join(cwd, "Dockerfile")
        with open(template_path, "w") as f:
            f.write(dockerfile_template)
        
        if model_name is None:
            model_name = _get_model_name(model_path=model_path, run_id=run_id)
        image_name = "mlflow-model-{model_name}".format(model_name=model_name)
        image_uri = "/".join([target_registry_uri.strip("/"), image_name])
        
        build_image(image_name=image_uri, template_path=template_path)
        if push_image:
            push_docker_image(image_uri=image_uri)

    output_directory = output_directory if output_directory is not None else os.getcwd()
    os.makedirs(output_directory)

    deployment_config_subpath = "{model_name}-deployment.yaml".format(model_name=model_name)
    service_config_subpath = "{model_name}-service.yaml".format(model_name=model_name)
    deployment_config_fullpath = os.path.join(output_directory, deployment_config_subpath)
    service_config_fullpath = os.path.join(output_directory, service_config_subpath)

    deployment_config = _get_deployment_config(model_name=model_name, image_uri=image_uri, 
            internal_port=MODEL_SERVER_INTERNAL_PORT)
    if image_pull_secret is not None:
        deployment_config = _add_image_pull_secret(
                deployment_config=deployment_config, secret_name=image_pull_secret)
    with open(deployment_config_fullpath, "w") as f:
        f.write(deployment_config)

    service_port = port if port is not None else DEFAULT_SERVICE_PORT 
    service_config = _get_service_config(model_name=model_name, service_port=service_port,
                internal_port=MODEL_SERVER_INTERNAL_PORT)
    with open(service_config_fullpath, "w") as f:
        f.write(service_config)

    model_server_config_fullpath = os.path.join(output_directory, SERVER_CONFIG_SUBPATH)
    model_server_config = ModelServerConfig(deployment_config_subpath=deployment_config_subpath,
                                             service_config_subpath=service_config_subpath)
    model_server_config.save(path=model_server_config_fullpath)

        
def _get_image_template(image_resources_path, model_path, run_id=None, pyfunc_uri=None, 
        mlflow_home=None):
    if pyfunc_uri is not None:
        dockerfile_cmds = ["FROM {base_uri}".format(base_uri=pyfunc_uri)]
    else:
        dockerfile_template = get_template(
                image_resources_path=image_resources_path, mlflow_home=mlflow_home)
        dockerfile_cmds = dockerfile_template.split("\n")

    if run_id:
        model_path = _get_model_log_dir(model_path, run_id)
        model_resource_path = _copy_file_or_tree(
                src=model_path, dst=image_resources_path, dst_dir="model")
         
    container_model_path = "/opt/ml/model"
    dockerfile_cmds.append("RUN rm -rf {container_model_path}".format(
        container_model_path=container_model_path))
    dockerfile_cmds.append("COPY {host_model_path} {container_model_path}".format(
        host_model_path=model_resource_path, container_model_path=container_model_path)) 
    return "\n".join(dockerfile_cmds)

    
def _get_model_name(model_path, run_id=None):
    return "{mp}-{rid}".format(mp=model_path,
                               rid=(run_id if run_id is not None else "local"))


def _get_deployment_config(model_name, image_uri, internal_port):
    return DEPLOYMENT_CONFIG_TEMPLATE.format(model_name=model_name, image_uri=image_uri, 
            internal_port=internal_port)


def _get_service_config(model_name, service_port, internal_port):
    return SERVICE_CONFIG_TEMPLATE.format(model_name=model_name, service_port=service_port, 
            internal_port=internal_port)


def _add_image_pull_secret(deployment_config, secret_name):
    """
    :param deployment_config: The deployment configuration string.
    :param secret_name: The name of the secret to add. 

    :return: The deployment configuration with the specified image pull secret.
    """
    parsed_config = yaml.safe_load(deployment_config)
    container_template_spec = parsed_config["spec"]["template"]["spec"]
    container_template_spec["imagePullSecrets"] = [{"name" : secret_name}]
    return yaml.dump(parsed_config, default_flow_style=False)


def _load_kubernetes_config(config_path):
    """
    :param config_path: The absolute path to the configuration.
    """
    with open(config_path, "r") as f:
        return yaml.load(f)
