# --------------------------------------------------------------------------
#
# Copyright (c) Microsoft Corporation. All rights reserved.
#
# The MIT License (MIT)
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the ""Software""), to
# deal in the Software without restriction, including without limitation the
# rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
# sell copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED *AS IS*, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
# IN THE SOFTWARE.
#
# --------------------------------------------------------------------------
import logging
from functools import lru_cache
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    Mapping,
    Optional,
    Type,
    overload,
    Union,
)
from ._utils import (  # pylint: disable=import-error
    validate_schema,
    create_message_content,
    validate_message,
    decode_content,
    MessageType
)

from ._apache_avro_encoder import (  # pylint: disable=import-error
    ApacheAvroObjectEncoder as AvroObjectEncoder,
)
from ._message_protocol import (  # pylint: disable=import-error
    MessageContent,
)

if TYPE_CHECKING:
    from azure.schemaregistry import SchemaRegistryClient

_LOGGER = logging.getLogger(__name__)


class AvroEncoder(object):
    """
    AvroEncoder provides the ability to encode and decode content according
    to the given avro schema. It would automatically register, get and cache the schema.

    :keyword client: Required. The schema registry client which is used to register schema
     and retrieve schema from the service.
    :paramtype client: ~azure.schemaregistry.SchemaRegistryClient
    :keyword Optional[str] group_name: Required for encoding. Not used for decoding.
     Schema group under which schema should be registered.
    :keyword bool auto_register: When true, register new schemas passed to encode.
     Otherwise, and by default, encode will fail if the schema has not been pre-registered in the registry.

    """

    def __init__(self, **kwargs):
        # type: (Any) -> None
        try:
            self._schema_registry_client = kwargs.pop(
                "client"
            )  # type: "SchemaRegistryClient"
        except KeyError as exc:
            raise TypeError(f"'{exc.args[0]}' is a required keyword.")
        self._avro_encoder = AvroObjectEncoder(codec=kwargs.get("codec"))
        self._schema_group = kwargs.pop("group_name", None)
        self._auto_register = kwargs.get("auto_register", False)
        self._auto_register_schema_func = (
            self._schema_registry_client.register_schema
            if self._auto_register
            else self._schema_registry_client.get_schema_properties
        )

    def __enter__(self):
        # type: () -> AvroEncoder
        self._schema_registry_client.__enter__()
        return self

    def __exit__(self, *exc_details):
        # type: (Any) -> None
        self._schema_registry_client.__exit__(*exc_details)

    def close(self):
        # type: () -> None
        """This method is to close the sockets opened by the client.
        It need not be used when using with a context manager.
        """
        self._schema_registry_client.close()

    @lru_cache(maxsize=128)
    def _get_schema_id(self, schema_name, schema_str, **kwargs):
        # type: (str, str, Any) -> str
        """
        Get schema id from local cache with the given schema.
        If there is no item in the local cache, get schema id from the service and cache it.

        :param schema_name: Name of the schema
        :type schema_name: str
        :param str schema_str: Schema string
        :return: Schema Id
        :rtype: str
        """
        schema_id = self._auto_register_schema_func(
            self._schema_group, schema_name, schema_str, "Avro", **kwargs
        ).id
        return schema_id

    @lru_cache(maxsize=128)
    def _get_schema(self, schema_id, **kwargs):
        # type: (str, Any) -> str
        """
        Get schema content from local cache with the given schema id.
        If there is no item in the local cache, get schema from the service and cache it.

        :param str schema_id: Schema id
        :return: Schema content
        :rtype: str
        """
        schema_str = self._schema_registry_client.get_schema(
            schema_id, **kwargs
        ).definition
        return schema_str

    @overload
    def encode(
        self,
        content: Mapping[str, Any],
        *,
        schema: str,
        message_type: Type[MessageType],
        request_options: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> MessageType:
        ...

    @overload
    def encode(
        self,
        content: Mapping[str, Any],
        *,
        schema: str,
        message_type: None = None,
        request_options: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> MessageContent:
        ...

    def encode(
        self,
        content: Mapping[str, Any],
        *,
        schema: str,
        message_type: Optional[Type[MessageType]] = None,
        request_options: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Union[MessageType, MessageContent]:
        """
        Encode content with the given schema. Create content type value, which consists of the Avro Mime Type string
         and the schema ID corresponding to given schema. If provided with a MessageType subtype, encoded content
         and content type will be passed to create message object. If not provided, the following dict will be returned:
         {"content": Avro encoded value, "content_type": Avro mime type string + schema ID}.

        If `message_type` is set, then additional keyword arguments will be passed to the message callback
         function provided.

        Schema must be an Avro RecordSchema:
        https://avro.apache.org/docs/1.10.0/gettingstartedpython.html#Defining+a+schema

        :param content: The content to be encoded.
        :type content: Mapping[str, Any]
        :keyword schema: Required. The schema used to encode the content.
        :paramtype schema: str
        :keyword message_type: The message class to construct the message. Must be a subtype of the
         azure.schemaregistry.encoder.avroencoder.MessageType protocol.
        :paramtype message_type: Type[MessageType] or None
        :keyword request_options: The keyword arguments for http requests to be passed to the client.
        :paramtype request_options: Dict[str, Any]
        :rtype: MessageType or MessageContent
        :raises ~azure.schemaregistry.encoder.avroencoder.InvalidSchemaError:
            Indicates an issue with validating schema.
        :raises ~azure.schemaregistry.encoder.avroencoder.InvalidContentError:
            Indicates an issue with encoding content with schema.
        """

        raw_input_schema = schema
        if not self._schema_group:
            raise TypeError("'group_name' in constructor cannot be None, if encoding.")
        schema_fullname = validate_schema(self._avro_encoder, raw_input_schema)

        cache_misses = (
            self._get_schema_id.cache_info().misses  # pylint: disable=no-value-for-parameter
        )
        request_options = request_options or {}
        schema_id = self._get_schema_id(
            schema_fullname, raw_input_schema, **request_options
        )
        new_cache_misses = (
            self._get_schema_id.cache_info().misses  # pylint: disable=no-value-for-parameter
        )
        if new_cache_misses > cache_misses:
            cache_info = (
                self._get_schema_id.cache_info()  # pylint: disable=no-value-for-parameter
            )
            _LOGGER.info(
                "New entry has been added to schema ID cache. Cache info: %s",
                str(cache_info),
            )

        return create_message_content(
            self._avro_encoder,
            content=content,
            raw_input_schema=raw_input_schema,
            schema_id=schema_id,
            message_type=message_type,
            **kwargs,
        )

    def decode(
        self,  # pylint: disable=unused-argument
        message: Union[MessageContent, MessageType],
        *,
        readers_schema: Optional[str] = None,
        request_options: Dict[str, Any] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Decode bytes content using schema ID in the content type field. `message` must be one of the following:
            1) An object of subtype of the MessageType protocol.
            2) A dict {"content": ..., "content_type": ...}, where "content" is bytes and "content_type" is string.
        Content must follow format of associated Avro RecordSchema:
        https://avro.apache.org/docs/1.10.0/gettingstartedpython.html#Defining+a+schema

        :param message: The message object which holds the content to be decoded and content type
         containing the schema ID.
        :type message: MessageType or MessageContent
        :keyword readers_schema: An optional reader's schema as defined by the Apache Avro specification.
        :paramtype readers_schema: str or None
        :keyword request_options: The keyword arguments for http requests to be passed to the client.
        :paramtype request_options: Dict[str, Any]
        :rtype: Dict[str, Any]
        :raises ~azure.schemaregistry.encoder.avroencoder.InvalidSchemaError:
            Indicates an issue with validating schemas.
        :raises ~azure.schemaregistry.encoder.avroencoder.InvalidContentError:
            Indicates an issue with decoding content.
        """
        schema_id, content = validate_message(message)
        cache_misses = (
            self._get_schema.cache_info().misses  # pylint: disable=no-value-for-parameter
        )
        request_options = request_options or {}
        schema_definition = self._get_schema(schema_id, **request_options)
        new_cache_misses = (
            self._get_schema.cache_info().misses  # pylint: disable=no-value-for-parameter
        )
        if new_cache_misses > cache_misses:
            cache_info = (
                self._get_schema.cache_info()  # pylint: disable=no-value-for-parameter
            )
            _LOGGER.info(
                "New entry has been added to schema cache. Cache info: %s",
                str(cache_info),
            )

        return decode_content(
            self._avro_encoder,
            content=content,
            schema_id=schema_id,
            schema_definition=schema_definition,
            readers_schema=readers_schema,
        )
