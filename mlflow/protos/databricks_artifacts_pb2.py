# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: databricks_artifacts.proto

import sys
_b=sys.version_info[0]<3 and (lambda x:x) or (lambda x:x.encode('latin1'))
from google.protobuf.internal import enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from google.protobuf import reflection as _reflection
from google.protobuf import symbol_database as _symbol_database
from google.protobuf import service as _service
from google.protobuf import service_reflection
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from .scalapb import scalapb_pb2 as scalapb_dot_scalapb__pb2
from . import databricks_pb2 as databricks__pb2


DESCRIPTOR = _descriptor.FileDescriptor(
  name='databricks_artifacts.proto',
  package='mlflow',
  syntax='proto2',
  serialized_options=_b('\n\037com.databricks.api.proto.mlflow\220\001\001\240\001\001\342?\002\020\001'),
  serialized_pb=_b('\n\x1a\x64\x61tabricks_artifacts.proto\x12\x06mlflow\x1a\x15scalapb/scalapb.proto\x1a\x10\x64\x61tabricks.proto\"\xdf\x01\n\x16\x41rtifactCredentialInfo\x12\x0e\n\x06run_id\x18\x01 \x01(\t\x12\x0c\n\x04path\x18\x02 \x01(\t\x12\x12\n\nsigned_uri\x18\x03 \x01(\t\x12:\n\x07headers\x18\x04 \x03(\x0b\x32).mlflow.ArtifactCredentialInfo.HttpHeader\x12,\n\x04type\x18\x05 \x01(\x0e\x32\x1e.mlflow.ArtifactCredentialType\x1a)\n\nHttpHeader\x12\x0c\n\x04name\x18\x01 \x01(\t\x12\r\n\x05value\x18\x02 \x01(\t\"\x90\x02\n\x15GetCredentialsForRead\x12\x14\n\x06run_id\x18\x01 \x01(\tB\x04\xf8\x86\x19\x01\x12\x12\n\x04path\x18\x02 \x03(\tB\x04\xf8\x86\x19\x01\x12\x12\n\npage_token\x18\x03 \x01(\t\x1aX\n\x08Response\x12\x33\n\x0b\x63redentials\x18\x01 \x03(\x0b\x32\x1e.mlflow.ArtifactCredentialInfo\x12\x17\n\x0fnext_page_token\x18\x02 \x01(\t:_\xe2?(\n&com.databricks.rpc.RPC[$this.Response]\xe2?1\n/com.databricks.mlflow.api.MlflowTrackingMessage\"\x91\x02\n\x16GetCredentialsForWrite\x12\x14\n\x06run_id\x18\x01 \x01(\tB\x04\xf8\x86\x19\x01\x12\x12\n\x04path\x18\x02 \x03(\tB\x04\xf8\x86\x19\x01\x12\x12\n\npage_token\x18\x03 \x01(\t\x1aX\n\x08Response\x12\x33\n\x0b\x63redentials\x18\x01 \x03(\x0b\x32\x1e.mlflow.ArtifactCredentialInfo\x12\x17\n\x0fnext_page_token\x18\x02 \x01(\t:_\xe2?(\n&com.databricks.rpc.RPC[$this.Response]\xe2?1\n/com.databricks.mlflow.api.MlflowTrackingMessage*V\n\x16\x41rtifactCredentialType\x12\x11\n\rAZURE_SAS_URI\x10\x01\x12\x15\n\x11\x41WS_PRESIGNED_URL\x10\x02\x12\x12\n\x0eGCP_SIGNED_URL\x10\x03\x32\xe2\x02\n DatabricksMlflowArtifactsService\x12\x9b\x01\n\x15getCredentialsForRead\x12\x1d.mlflow.GetCredentialsForRead\x1a&.mlflow.GetCredentialsForRead.Response\";\xf2\x86\x19\x37\n3\n\x03GET\x12&/mlflow/artifacts/credentials-for-read\x1a\x04\x08\x02\x10\x00\x10\x03\x12\x9f\x01\n\x16getCredentialsForWrite\x12\x1e.mlflow.GetCredentialsForWrite\x1a\'.mlflow.GetCredentialsForWrite.Response\"<\xf2\x86\x19\x38\n4\n\x03GET\x12\'/mlflow/artifacts/credentials-for-write\x1a\x04\x08\x02\x10\x00\x10\x03\x42,\n\x1f\x63om.databricks.api.proto.mlflow\x90\x01\x01\xa0\x01\x01\xe2?\x02\x10\x01')
  ,
  dependencies=[scalapb_dot_scalapb__pb2.DESCRIPTOR,databricks__pb2.DESCRIPTOR,])

_ARTIFACTCREDENTIALTYPE = _descriptor.EnumDescriptor(
  name='ArtifactCredentialType',
  full_name='mlflow.ArtifactCredentialType',
  filename=None,
  file=DESCRIPTOR,
  values=[
    _descriptor.EnumValueDescriptor(
      name='AZURE_SAS_URI', index=0, number=1,
      serialized_options=None,
      type=None),
    _descriptor.EnumValueDescriptor(
      name='AWS_PRESIGNED_URL', index=1, number=2,
      serialized_options=None,
      type=None),
    _descriptor.EnumValueDescriptor(
      name='GCP_SIGNED_URL', index=2, number=3,
      serialized_options=None,
      type=None),
  ],
  containing_type=None,
  serialized_options=None,
  serialized_start=856,
  serialized_end=942,
)
_sym_db.RegisterEnumDescriptor(_ARTIFACTCREDENTIALTYPE)

ArtifactCredentialType = enum_type_wrapper.EnumTypeWrapper(_ARTIFACTCREDENTIALTYPE)
AZURE_SAS_URI = 1
AWS_PRESIGNED_URL = 2
GCP_SIGNED_URL = 3



_ARTIFACTCREDENTIALINFO_HTTPHEADER = _descriptor.Descriptor(
  name='HttpHeader',
  full_name='mlflow.ArtifactCredentialInfo.HttpHeader',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  fields=[
    _descriptor.FieldDescriptor(
      name='name', full_name='mlflow.ArtifactCredentialInfo.HttpHeader.name', index=0,
      number=1, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=_b("").decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='value', full_name='mlflow.ArtifactCredentialInfo.HttpHeader.value', index=1,
      number=2, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=_b("").decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
  ],
  extensions=[
  ],
  nested_types=[],
  enum_types=[
  ],
  serialized_options=None,
  is_extendable=False,
  syntax='proto2',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=262,
  serialized_end=303,
)

_ARTIFACTCREDENTIALINFO = _descriptor.Descriptor(
  name='ArtifactCredentialInfo',
  full_name='mlflow.ArtifactCredentialInfo',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  fields=[
    _descriptor.FieldDescriptor(
      name='run_id', full_name='mlflow.ArtifactCredentialInfo.run_id', index=0,
      number=1, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=_b("").decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='path', full_name='mlflow.ArtifactCredentialInfo.path', index=1,
      number=2, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=_b("").decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='signed_uri', full_name='mlflow.ArtifactCredentialInfo.signed_uri', index=2,
      number=3, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=_b("").decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='headers', full_name='mlflow.ArtifactCredentialInfo.headers', index=3,
      number=4, type=11, cpp_type=10, label=3,
      has_default_value=False, default_value=[],
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='type', full_name='mlflow.ArtifactCredentialInfo.type', index=4,
      number=5, type=14, cpp_type=8, label=1,
      has_default_value=False, default_value=1,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
  ],
  extensions=[
  ],
  nested_types=[_ARTIFACTCREDENTIALINFO_HTTPHEADER, ],
  enum_types=[
  ],
  serialized_options=None,
  is_extendable=False,
  syntax='proto2',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=80,
  serialized_end=303,
)


_GETCREDENTIALSFORREAD_RESPONSE = _descriptor.Descriptor(
  name='Response',
  full_name='mlflow.GetCredentialsForRead.Response',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  fields=[
    _descriptor.FieldDescriptor(
      name='credentials', full_name='mlflow.GetCredentialsForRead.Response.credentials', index=0,
      number=1, type=11, cpp_type=10, label=3,
      has_default_value=False, default_value=[],
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='next_page_token', full_name='mlflow.GetCredentialsForRead.Response.next_page_token', index=1,
      number=2, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=_b("").decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
  ],
  extensions=[
  ],
  nested_types=[],
  enum_types=[
  ],
  serialized_options=None,
  is_extendable=False,
  syntax='proto2',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=393,
  serialized_end=481,
)

_GETCREDENTIALSFORREAD = _descriptor.Descriptor(
  name='GetCredentialsForRead',
  full_name='mlflow.GetCredentialsForRead',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  fields=[
    _descriptor.FieldDescriptor(
      name='run_id', full_name='mlflow.GetCredentialsForRead.run_id', index=0,
      number=1, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=_b("").decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=_b('\370\206\031\001'), file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='path', full_name='mlflow.GetCredentialsForRead.path', index=1,
      number=2, type=9, cpp_type=9, label=3,
      has_default_value=False, default_value=[],
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=_b('\370\206\031\001'), file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='page_token', full_name='mlflow.GetCredentialsForRead.page_token', index=2,
      number=3, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=_b("").decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
  ],
  extensions=[
  ],
  nested_types=[_GETCREDENTIALSFORREAD_RESPONSE, ],
  enum_types=[
  ],
  serialized_options=_b('\342?(\n&com.databricks.rpc.RPC[$this.Response]\342?1\n/com.databricks.mlflow.api.MlflowTrackingMessage'),
  is_extendable=False,
  syntax='proto2',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=306,
  serialized_end=578,
)


_GETCREDENTIALSFORWRITE_RESPONSE = _descriptor.Descriptor(
  name='Response',
  full_name='mlflow.GetCredentialsForWrite.Response',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  fields=[
    _descriptor.FieldDescriptor(
      name='credentials', full_name='mlflow.GetCredentialsForWrite.Response.credentials', index=0,
      number=1, type=11, cpp_type=10, label=3,
      has_default_value=False, default_value=[],
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='next_page_token', full_name='mlflow.GetCredentialsForWrite.Response.next_page_token', index=1,
      number=2, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=_b("").decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
  ],
  extensions=[
  ],
  nested_types=[],
  enum_types=[
  ],
  serialized_options=None,
  is_extendable=False,
  syntax='proto2',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=393,
  serialized_end=481,
)

_GETCREDENTIALSFORWRITE = _descriptor.Descriptor(
  name='GetCredentialsForWrite',
  full_name='mlflow.GetCredentialsForWrite',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  fields=[
    _descriptor.FieldDescriptor(
      name='run_id', full_name='mlflow.GetCredentialsForWrite.run_id', index=0,
      number=1, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=_b("").decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=_b('\370\206\031\001'), file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='path', full_name='mlflow.GetCredentialsForWrite.path', index=1,
      number=2, type=9, cpp_type=9, label=3,
      has_default_value=False, default_value=[],
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=_b('\370\206\031\001'), file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='page_token', full_name='mlflow.GetCredentialsForWrite.page_token', index=2,
      number=3, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=_b("").decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
  ],
  extensions=[
  ],
  nested_types=[_GETCREDENTIALSFORWRITE_RESPONSE, ],
  enum_types=[
  ],
  serialized_options=_b('\342?(\n&com.databricks.rpc.RPC[$this.Response]\342?1\n/com.databricks.mlflow.api.MlflowTrackingMessage'),
  is_extendable=False,
  syntax='proto2',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=581,
  serialized_end=854,
)

_ARTIFACTCREDENTIALINFO_HTTPHEADER.containing_type = _ARTIFACTCREDENTIALINFO
_ARTIFACTCREDENTIALINFO.fields_by_name['headers'].message_type = _ARTIFACTCREDENTIALINFO_HTTPHEADER
_ARTIFACTCREDENTIALINFO.fields_by_name['type'].enum_type = _ARTIFACTCREDENTIALTYPE
_GETCREDENTIALSFORREAD_RESPONSE.fields_by_name['credentials'].message_type = _ARTIFACTCREDENTIALINFO
_GETCREDENTIALSFORREAD_RESPONSE.containing_type = _GETCREDENTIALSFORREAD
_GETCREDENTIALSFORWRITE_RESPONSE.fields_by_name['credentials'].message_type = _ARTIFACTCREDENTIALINFO
_GETCREDENTIALSFORWRITE_RESPONSE.containing_type = _GETCREDENTIALSFORWRITE
DESCRIPTOR.message_types_by_name['ArtifactCredentialInfo'] = _ARTIFACTCREDENTIALINFO
DESCRIPTOR.message_types_by_name['GetCredentialsForRead'] = _GETCREDENTIALSFORREAD
DESCRIPTOR.message_types_by_name['GetCredentialsForWrite'] = _GETCREDENTIALSFORWRITE
DESCRIPTOR.enum_types_by_name['ArtifactCredentialType'] = _ARTIFACTCREDENTIALTYPE
_sym_db.RegisterFileDescriptor(DESCRIPTOR)

ArtifactCredentialInfo = _reflection.GeneratedProtocolMessageType('ArtifactCredentialInfo', (_message.Message,), dict(

  HttpHeader = _reflection.GeneratedProtocolMessageType('HttpHeader', (_message.Message,), dict(
    DESCRIPTOR = _ARTIFACTCREDENTIALINFO_HTTPHEADER,
    __module__ = 'databricks_artifacts_pb2'
    # @@protoc_insertion_point(class_scope:mlflow.ArtifactCredentialInfo.HttpHeader)
    ))
  ,
  DESCRIPTOR = _ARTIFACTCREDENTIALINFO,
  __module__ = 'databricks_artifacts_pb2'
  # @@protoc_insertion_point(class_scope:mlflow.ArtifactCredentialInfo)
  ))
_sym_db.RegisterMessage(ArtifactCredentialInfo)
_sym_db.RegisterMessage(ArtifactCredentialInfo.HttpHeader)

GetCredentialsForRead = _reflection.GeneratedProtocolMessageType('GetCredentialsForRead', (_message.Message,), dict(

  Response = _reflection.GeneratedProtocolMessageType('Response', (_message.Message,), dict(
    DESCRIPTOR = _GETCREDENTIALSFORREAD_RESPONSE,
    __module__ = 'databricks_artifacts_pb2'
    # @@protoc_insertion_point(class_scope:mlflow.GetCredentialsForRead.Response)
    ))
  ,
  DESCRIPTOR = _GETCREDENTIALSFORREAD,
  __module__ = 'databricks_artifacts_pb2'
  # @@protoc_insertion_point(class_scope:mlflow.GetCredentialsForRead)
  ))
_sym_db.RegisterMessage(GetCredentialsForRead)
_sym_db.RegisterMessage(GetCredentialsForRead.Response)

GetCredentialsForWrite = _reflection.GeneratedProtocolMessageType('GetCredentialsForWrite', (_message.Message,), dict(

  Response = _reflection.GeneratedProtocolMessageType('Response', (_message.Message,), dict(
    DESCRIPTOR = _GETCREDENTIALSFORWRITE_RESPONSE,
    __module__ = 'databricks_artifacts_pb2'
    # @@protoc_insertion_point(class_scope:mlflow.GetCredentialsForWrite.Response)
    ))
  ,
  DESCRIPTOR = _GETCREDENTIALSFORWRITE,
  __module__ = 'databricks_artifacts_pb2'
  # @@protoc_insertion_point(class_scope:mlflow.GetCredentialsForWrite)
  ))
_sym_db.RegisterMessage(GetCredentialsForWrite)
_sym_db.RegisterMessage(GetCredentialsForWrite.Response)


DESCRIPTOR._options = None
_GETCREDENTIALSFORREAD.fields_by_name['run_id']._options = None
_GETCREDENTIALSFORREAD.fields_by_name['path']._options = None
_GETCREDENTIALSFORREAD._options = None
_GETCREDENTIALSFORWRITE.fields_by_name['run_id']._options = None
_GETCREDENTIALSFORWRITE.fields_by_name['path']._options = None
_GETCREDENTIALSFORWRITE._options = None

_DATABRICKSMLFLOWARTIFACTSSERVICE = _descriptor.ServiceDescriptor(
  name='DatabricksMlflowArtifactsService',
  full_name='mlflow.DatabricksMlflowArtifactsService',
  file=DESCRIPTOR,
  index=0,
  serialized_options=None,
  serialized_start=945,
  serialized_end=1299,
  methods=[
  _descriptor.MethodDescriptor(
    name='getCredentialsForRead',
    full_name='mlflow.DatabricksMlflowArtifactsService.getCredentialsForRead',
    index=0,
    containing_service=None,
    input_type=_GETCREDENTIALSFORREAD,
    output_type=_GETCREDENTIALSFORREAD_RESPONSE,
    serialized_options=_b('\362\206\0317\n3\n\003GET\022&/mlflow/artifacts/credentials-for-read\032\004\010\002\020\000\020\003'),
  ),
  _descriptor.MethodDescriptor(
    name='getCredentialsForWrite',
    full_name='mlflow.DatabricksMlflowArtifactsService.getCredentialsForWrite',
    index=1,
    containing_service=None,
    input_type=_GETCREDENTIALSFORWRITE,
    output_type=_GETCREDENTIALSFORWRITE_RESPONSE,
    serialized_options=_b('\362\206\0318\n4\n\003GET\022\'/mlflow/artifacts/credentials-for-write\032\004\010\002\020\000\020\003'),
  ),
])
_sym_db.RegisterServiceDescriptor(_DATABRICKSMLFLOWARTIFACTSSERVICE)

DESCRIPTOR.services_by_name['DatabricksMlflowArtifactsService'] = _DATABRICKSMLFLOWARTIFACTSSERVICE

DatabricksMlflowArtifactsService = service_reflection.GeneratedServiceType('DatabricksMlflowArtifactsService', (_service.Service,), dict(
  DESCRIPTOR = _DATABRICKSMLFLOWARTIFACTSSERVICE,
  __module__ = 'databricks_artifacts_pb2'
  ))

DatabricksMlflowArtifactsService_Stub = service_reflection.GeneratedServiceStubType('DatabricksMlflowArtifactsService_Stub', (DatabricksMlflowArtifactsService,), dict(
  DESCRIPTOR = _DATABRICKSMLFLOWARTIFACTSSERVICE,
  __module__ = 'databricks_artifacts_pb2'
  ))


# @@protoc_insertion_point(module_scope)
