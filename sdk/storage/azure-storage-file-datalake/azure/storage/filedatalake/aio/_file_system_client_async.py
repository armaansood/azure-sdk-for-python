# pylint: disable=too-many-lines
# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
# --------------------------------------------------------------------------
# pylint: disable=invalid-overridden-method
import functools
from typing import (  # pylint: disable=unused-import
    Union, Optional, Any, Dict,
    TYPE_CHECKING
)

from azure.core.exceptions import HttpResponseError
from azure.core.tracing.decorator import distributed_trace

from azure.core.pipeline import AsyncPipeline
from azure.core.async_paging import AsyncItemPaged

from azure.core.tracing.decorator_async import distributed_trace_async
from azure.storage.blob.aio import ContainerClient
from .._serialize import get_api_version
from .._deserialize import process_storage_error, is_file_path
from .._generated.models import ListBlobsIncludeItem

from ._data_lake_file_client_async import DataLakeFileClient
from ._data_lake_directory_client_async import DataLakeDirectoryClient
from ._data_lake_lease_async import DataLakeLeaseClient
from .._file_system_client import FileSystemClient as FileSystemClientBase
from .._generated.aio import AzureDataLakeStorageRESTAPI
from .._shared.base_client_async import AsyncTransportWrapper, AsyncStorageAccountHostsMixin
from .._shared.policies_async import ExponentialRetry
from .._models import FileSystemProperties, PublicAccess, DirectoryProperties, FileProperties, DeletedPathProperties
from ._list_paths_helper import DeletedPathPropertiesPaged, PathPropertiesPaged


if TYPE_CHECKING:
    from datetime import datetime
    from .._models import (  # pylint: disable=unused-import
        ContentSettings)


class FileSystemClient(AsyncStorageAccountHostsMixin, FileSystemClientBase):
    """A client to interact with a specific file system, even if that file system
     may not yet exist.

     For operations relating to a specific directory or file within this file system, a directory client or file client
     can be retrieved using the :func:`~get_directory_client` or :func:`~get_file_client` functions.

     :ivar str url:
         The full endpoint URL to the file system, including SAS token if used.
     :ivar str primary_endpoint:
         The full primary endpoint URL.
     :ivar str primary_hostname:
         The hostname of the primary endpoint.
     :param str account_url:
         The URI to the storage account.
     :param file_system_name:
         The file system for the directory or files.
     :type file_system_name: str
     :param credential:
         The credentials with which to authenticate. This is optional if the
         account URL already has a SAS token. The value can be a SAS token string,
         an instance of a AzureSasCredential from azure.core.credentials, an account
         shared access key, or an instance of a TokenCredentials class from azure.identity.
         If the resource URI already contains a SAS token, this will be ignored in favor of an explicit credential
         - except in the case of AzureSasCredential, where the conflicting SAS tokens will raise a ValueError.
     :keyword str api_version:
        The Storage API version to use for requests. Default value is the most recent service version that is
        compatible with the current SDK. Setting to an older version may result in reduced feature compatibility.

    .. admonition:: Example:

        .. literalinclude:: ../samples/datalake_samples_file_system_async.py
            :start-after: [START create_file_system_client_from_service]
            :end-before: [END create_file_system_client_from_service]
            :language: python
            :dedent: 8
            :caption: Get a FileSystemClient from an existing DataLakeServiceClient.
     """

    def __init__(
            self, account_url,  # type: str
            file_system_name,  # type: str
            credential=None,  # type: Optional[Any]
            **kwargs  # type: Any
    ):
        # type: (...) -> None
        kwargs['retry_policy'] = kwargs.get('retry_policy') or ExponentialRetry(**kwargs)
        super(FileSystemClient, self).__init__(
            account_url,
            file_system_name=file_system_name,
            credential=credential,
            **kwargs)
        # to override the class field _container_client sync version
        kwargs.pop('_hosts', None)
        self._container_client = ContainerClient(self._blob_account_url, self.file_system_name,
                                                 credential=credential,
                                                 _hosts=self._container_client._hosts,# pylint: disable=protected-access
                                                 **kwargs)  # type: ignore # pylint: disable=protected-access
        self._client = AzureDataLakeStorageRESTAPI(self.url, base_url=self.url,
                                                   file_system=self.file_system_name, pipeline=self._pipeline)
        self._datalake_client_for_blob_operation = AzureDataLakeStorageRESTAPI(self._container_client.url,
                                                                               base_url=self._container_client.url,
                                                                               file_system=self.file_system_name,
                                                                               pipeline=self._pipeline)
        api_version = get_api_version(kwargs)
        self._client._config.version = api_version  # pylint: disable=protected-access
        self._datalake_client_for_blob_operation._config.version = api_version  # pylint: disable=protected-access

        self._loop = kwargs.get('loop', None)

    async def __aexit__(self, *args):
        await self._container_client.close()
        await super(FileSystemClient, self).__aexit__(*args)

    async def close(self):
        # type: () -> None
        """ This method is to close the sockets opened by the client.
        It need not be used when using with a context manager.
        """
        await self._container_client.close()
        await self.__aexit__()

    @distributed_trace_async
    async def acquire_lease(
            self, lease_duration=-1,  # type: int
            lease_id=None,  # type: Optional[str]
            **kwargs
    ):
        # type: (...) -> DataLakeLeaseClient
        """
        Requests a new lease. If the file system does not have an active lease,
        the DataLake service creates a lease on the file system and returns a new
        lease ID.

        :param int lease_duration:
            Specifies the duration of the lease, in seconds, or negative one
            (-1) for a lease that never expires. A non-infinite lease can be
            between 15 and 60 seconds. A lease duration cannot be changed
            using renew or change. Default is -1 (infinite lease).
        :param str lease_id:
            Proposed lease ID, in a GUID string format. The DataLake service returns
            400 (Invalid request) if the proposed lease ID is not in the correct format.
        :keyword ~datetime.datetime if_modified_since:
            A DateTime value. Azure expects the date value passed in to be UTC.
            If timezone is included, any non-UTC datetimes will be converted to UTC.
            If a date is passed in without timezone info, it is assumed to be UTC.
            Specify this header to perform the operation only
            if the resource has been modified since the specified time.
        :keyword ~datetime.datetime if_unmodified_since:
            A DateTime value. Azure expects the date value passed in to be UTC.
            If timezone is included, any non-UTC datetimes will be converted to UTC.
            If a date is passed in without timezone info, it is assumed to be UTC.
            Specify this header to perform the operation only if
            the resource has not been modified since the specified date/time.
        :keyword str etag:
            An ETag value, or the wildcard character (*). Used to check if the resource has changed,
            and act according to the condition specified by the `match_condition` parameter.
        :keyword ~azure.core.MatchConditions match_condition:
            The match condition to use upon the etag.
        :keyword int timeout:
            The timeout parameter is expressed in seconds.
        :returns: A DataLakeLeaseClient object, that can be run in a context manager.
        :rtype: ~azure.storage.filedatalake.aio.DataLakeLeaseClient

        .. admonition:: Example:

            .. literalinclude:: ../samples/datalake_samples_file_system_async.py
                :start-after: [START acquire_lease_on_file_system]
                :end-before: [END acquire_lease_on_file_system]
                :language: python
                :dedent: 12
                :caption: Acquiring a lease on the file_system.
        """
        lease = DataLakeLeaseClient(self, lease_id=lease_id)
        await lease.acquire(lease_duration=lease_duration, **kwargs)
        return lease

    @distributed_trace_async
    async def create_file_system(self, metadata=None,  # type: Optional[Dict[str, str]]
                                 public_access=None,  # type: Optional[PublicAccess]
                                 **kwargs):
        # type: (...) ->  Dict[str, Union[str, datetime]]
        """Creates a new file system under the specified account.

        If the file system with the same name already exists, a ResourceExistsError will
        be raised. This method returns a client with which to interact with the newly
        created file system.

        :param metadata:
            A dict with name-value pairs to associate with the
            file system as metadata. Example: `{'Category':'test'}`
        :type metadata: dict(str, str)
        :param public_access:
            To specify whether data in the file system may be accessed publicly and the level of access.
        :type public_access: ~azure.storage.filedatalake.PublicAccess
        :keyword int timeout:
            The timeout parameter is expressed in seconds.
        :rtype: None

        .. admonition:: Example:

            .. literalinclude:: ../samples/datalake_samples_file_system_async.py
                :start-after: [START create_file_system]
                :end-before: [END create_file_system]
                :language: python
                :dedent: 16
                :caption: Creating a file system in the datalake service.
        """
        return await self._container_client.create_container(metadata=metadata,
                                                             public_access=public_access,
                                                             **kwargs)

    @distributed_trace_async
    async def exists(self, **kwargs):
        # type: (**Any) -> bool
        """
        Returns True if a file system exists and returns False otherwise.

        :kwarg int timeout:
            The timeout parameter is expressed in seconds.
        :returns: boolean
        """
        return await self._container_client.exists(**kwargs)

    @distributed_trace_async
    async def _rename_file_system(self, new_name, **kwargs):
        # type: (str, **Any) -> FileSystemClient
        """Renames a filesystem.

        Operation is successful only if the source filesystem exists.

        :param str new_name:
            The new filesystem name the user wants to rename to.
        :keyword lease:
            Specify this to perform only if the lease ID given
            matches the active lease ID of the source filesystem.
        :paramtype lease: ~azure.storage.filedatalake.DataLakeLeaseClient or str
        :keyword int timeout:
            The timeout parameter is expressed in seconds.
        :rtype: ~azure.storage.filedatalake.FileSystemClient
        """
        await self._container_client._rename_container(new_name, **kwargs)   # pylint: disable=protected-access
        renamed_file_system = FileSystemClient(
                "{}://{}".format(self.scheme, self.primary_hostname), file_system_name=new_name,
                credential=self._raw_credential, api_version=self.api_version, _configuration=self._config,
                _pipeline=self._pipeline, _location_mode=self._location_mode, _hosts=self._hosts,
                require_encryption=self.require_encryption, key_encryption_key=self.key_encryption_key,
                key_resolver_function=self.key_resolver_function)
        return renamed_file_system

    @distributed_trace_async
    async def delete_file_system(self, **kwargs):
        # type: (Any) -> None
        """Marks the specified file system for deletion.

        The file system and any files contained within it are later deleted during garbage collection.
        If the file system is not found, a ResourceNotFoundError will be raised.

        :keyword lease:
            If specified, delete_file_system only succeeds if the
            file system's lease is active and matches this ID.
            Required if the file system has an active lease.
        :paramtype lease: ~azure.storage.filedatalake.aio.DataLakeLeaseClient or str
        :keyword ~datetime.datetime if_modified_since:
            A DateTime value. Azure expects the date value passed in to be UTC.
            If timezone is included, any non-UTC datetimes will be converted to UTC.
            If a date is passed in without timezone info, it is assumed to be UTC.
            Specify this header to perform the operation only
            if the resource has been modified since the specified time.
        :keyword ~datetime.datetime if_unmodified_since:
            A DateTime value. Azure expects the date value passed in to be UTC.
            If timezone is included, any non-UTC datetimes will be converted to UTC.
            If a date is passed in without timezone info, it is assumed to be UTC.
            Specify this header to perform the operation only if
            the resource has not been modified since the specified date/time.
        :keyword str etag:
            An ETag value, or the wildcard character (*). Used to check if the resource has changed,
            and act according to the condition specified by the `match_condition` parameter.
        :keyword ~azure.core.MatchConditions match_condition:
            The match condition to use upon the etag.
        :keyword int timeout:
            The timeout parameter is expressed in seconds.
        :rtype: None

        .. admonition:: Example:

            .. literalinclude:: ../samples/datalake_samples_file_system_async.py
                :start-after: [START delete_file_system]
                :end-before: [END delete_file_system]
                :language: python
                :dedent: 16
                :caption: Deleting a file system in the datalake service.
        """
        await self._container_client.delete_container(**kwargs)

    @distributed_trace_async
    async def get_file_system_properties(self, **kwargs):
        # type: (Any) -> FileSystemProperties
        """Returns all user-defined metadata and system properties for the specified
        file system. The data returned does not include the file system's list of paths.

        :keyword lease:
            If specified, get_file_system_properties only succeeds if the
            file system's lease is active and matches this ID.
        :paramtype lease: ~azure.storage.filedatalake.aio.DataLakeLeaseClient or str
        :keyword int timeout:
            The timeout parameter is expressed in seconds.
        :return: Properties for the specified file system within a file system object.
        :rtype: ~azure.storage.filedatalake.FileSystemProperties

        .. admonition:: Example:

            .. literalinclude:: ../samples/datalake_samples_file_system_async.py
                :start-after: [START get_file_system_properties]
                :end-before: [END get_file_system_properties]
                :language: python
                :dedent: 16
                :caption: Getting properties on the file system.
        """
        container_properties = await self._container_client.get_container_properties(**kwargs)
        return FileSystemProperties._convert_from_container_props(container_properties)  # pylint: disable=protected-access

    @distributed_trace_async
    async def set_file_system_metadata(  # type: ignore
            self, metadata,  # type: Dict[str, str]
            **kwargs
    ):
        # type: (...) -> Dict[str, Union[str, datetime]]
        """Sets one or more user-defined name-value pairs for the specified
        file system. Each call to this operation replaces all existing metadata
        attached to the file system. To remove all metadata from the file system,
        call this operation with no metadata dict.

        :param metadata:
            A dict containing name-value pairs to associate with the file system as
            metadata. Example: {'category':'test'}
        :type metadata: dict[str, str]
        :keyword lease:
            If specified, set_file_system_metadata only succeeds if the
            file system's lease is active and matches this ID.
        :paramtype lease: ~azure.storage.filedatalake.aio.DataLakeLeaseClient or str
        :keyword ~datetime.datetime if_modified_since:
            A DateTime value. Azure expects the date value passed in to be UTC.
            If timezone is included, any non-UTC datetimes will be converted to UTC.
            If a date is passed in without timezone info, it is assumed to be UTC.
            Specify this header to perform the operation only
            if the resource has been modified since the specified time.
        :keyword ~datetime.datetime if_unmodified_since:
            A DateTime value. Azure expects the date value passed in to be UTC.
            If timezone is included, any non-UTC datetimes will be converted to UTC.
            If a date is passed in without timezone info, it is assumed to be UTC.
            Specify this header to perform the operation only if
            the resource has not been modified since the specified date/time.
        :keyword str etag:
            An ETag value, or the wildcard character (*). Used to check if the resource has changed,
            and act according to the condition specified by the `match_condition` parameter.
        :keyword ~azure.core.MatchConditions match_condition:
            The match condition to use upon the etag.
        :keyword int timeout:
            The timeout parameter is expressed in seconds.
        :returns: file system-updated property dict (Etag and last modified).

        .. admonition:: Example:

            .. literalinclude:: ../samples/datalake_samples_file_system_async.py
                :start-after: [START set_file_system_metadata]
                :end-before: [END set_file_system_metadata]
                :language: python
                :dedent: 16
                :caption: Setting metadata on the container.
        """
        return await self._container_client.set_container_metadata(metadata=metadata, **kwargs)

    @distributed_trace_async
    async def set_file_system_access_policy(
            self, signed_identifiers,  # type: Dict[str, AccessPolicy]
            public_access=None,  # type: Optional[Union[str, PublicAccess]]
            **kwargs
    ):  # type: (...) -> Dict[str, Union[str, datetime]]
        """Sets the permissions for the specified file system or stored access
        policies that may be used with Shared Access Signatures. The permissions
        indicate whether files in a file system may be accessed publicly.

        :param signed_identifiers:
            A dictionary of access policies to associate with the file system. The
            dictionary may contain up to 5 elements. An empty dictionary
            will clear the access policies set on the service.
        :type signed_identifiers: dict[str, ~azure.storage.filedatalake.AccessPolicy]
        :param ~azure.storage.filedatalake.PublicAccess public_access:
            To specify whether data in the file system may be accessed publicly and the level of access.
        :keyword lease:
            Required if the file system has an active lease. Value can be a DataLakeLeaseClient object
            or the lease ID as a string.
        :paramtype lease: ~azure.storage.filedatalake.aio.DataLakeLeaseClient or str
        :keyword ~datetime.datetime if_modified_since:
            A datetime value. Azure expects the date value passed in to be UTC.
            If timezone is included, any non-UTC datetimes will be converted to UTC.
            If a date is passed in without timezone info, it is assumed to be UTC.
            Specify this header to perform the operation only
            if the resource has been modified since the specified date/time.
        :keyword ~datetime.datetime if_unmodified_since:
            A datetime value. Azure expects the date value passed in to be UTC.
            If timezone is included, any non-UTC datetimes will be converted to UTC.
            If a date is passed in without timezone info, it is assumed to be UTC.
            Specify this header to perform the operation only if
            the resource has not been modified since the specified date/time.
        :keyword int timeout:
            The timeout parameter is expressed in seconds.
        :returns: filesystem-updated property dict (Etag and last modified).
        :rtype: dict[str, str or ~datetime.datetime]
        """
        return await self._container_client.set_container_access_policy(signed_identifiers,
                                                                        public_access=public_access, **kwargs)

    @distributed_trace_async
    async def get_file_system_access_policy(self, **kwargs):
        # type: (Any) -> Dict[str, Any]
        """Gets the permissions for the specified file system.
        The permissions indicate whether file system data may be accessed publicly.

        :keyword lease:
            If specified, get_file_system_access_policy only succeeds if the
            file system's lease is active and matches this ID.
        :paramtype lease: ~azure.storage.filedatalake.aio.DataLakeLeaseClient or str
        :keyword int timeout:
            The timeout parameter is expressed in seconds.
        :returns: Access policy information in a dict.
        :rtype: dict[str, Any]
        """
        access_policy = await self._container_client.get_container_access_policy(**kwargs)
        return {
            'public_access': PublicAccess._from_generated(access_policy['public_access']),  # pylint: disable=protected-access
            'signed_identifiers': access_policy['signed_identifiers']
        }

    @distributed_trace
    def get_paths(self, path=None,  # type: Optional[str]
                        recursive=True,  # type: Optional[bool]
                        max_results=None,  # type: Optional[int]
                        **kwargs):
        # type: (...) -> AsyncItemPaged[PathProperties]
        """Returns a generator to list the paths(could be files or directories) under the specified file system.
        The generator will lazily follow the continuation tokens returned by
        the service.

        :param str path:
            Filters the results to return only paths under the specified path.
        :param int max_results:
            An optional value that specifies the maximum
            number of items to return per page. If omitted or greater than 5,000, the
            response will include up to 5,000 items per page.
        :keyword upn:
            Optional. Valid only when Hierarchical Namespace is
            enabled for the account. If "true", the user identity values returned
            in the x-ms-owner, x-ms-group, and x-ms-acl response headers will be
            transformed from Azure Active Directory Object IDs to User Principal
            Names.  If "false", the values will be returned as Azure Active
            Directory Object IDs. The default value is false. Note that group and
            application Object IDs are not translated because they do not have
            unique friendly names.
        :type upn: bool
        :keyword int timeout:
            The timeout parameter is expressed in seconds.
        :returns: An iterable (auto-paging) response of PathProperties.
        :rtype: ~azure.core.paging.ItemPaged[~azure.storage.filedatalake.PathProperties]

        .. admonition:: Example:

            .. literalinclude:: ../samples/datalake_samples_file_system_async.py
                :start-after: [START get_paths_in_file_system]
                :end-before: [END get_paths_in_file_system]
                :language: python
                :dedent: 12
                :caption: List the blobs in the file system.
        """
        timeout = kwargs.pop('timeout', None)
        command = functools.partial(
            self._client.file_system.list_paths,
            path=path,
            timeout=timeout,
            **kwargs)
        return AsyncItemPaged(
            command, recursive, path=path, max_results=max_results,
            page_iterator_class=PathPropertiesPaged, **kwargs)

    @distributed_trace_async
    async def create_directory(self, directory,  # type: Union[DirectoryProperties, str]
                               metadata=None,  # type: Optional[Dict[str, str]]
                               **kwargs):
        # type: (...) -> DataLakeDirectoryClient
        """
        Create directory

        :param directory:
            The directory with which to interact. This can either be the name of the directory,
            or an instance of DirectoryProperties.
        :type directory: str or ~azure.storage.filedatalake.DirectoryProperties
        :param metadata:
            Name-value pairs associated with the file as metadata.
        :type metadata: dict(str, str)
        :keyword ~azure.storage.filedatalake.ContentSettings content_settings:
            ContentSettings object used to set path properties.
        :keyword lease:
            Required if the file has an active lease. Value can be a DataLakeLeaseClient object
            or the lease ID as a string.
        :paramtype lease: ~azure.storage.filedatalake.aio.DataLakeLeaseClient or str
        :keyword str umask:
            Optional and only valid if Hierarchical Namespace is enabled for the account.
            When creating a file or directory and the parent folder does not have a default ACL,
            the umask restricts the permissions of the file or directory to be created.
            The resulting permission is given by p & ^u, where p is the permission and u is the umask.
            For example, if p is 0777 and u is 0057, then the resulting permission is 0720.
            The default permission is 0777 for a directory and 0666 for a file. The default umask is 0027.
            The umask must be specified in 4-digit octal notation (e.g. 0766).
        :keyword str permissions:
            Optional and only valid if Hierarchical Namespace
            is enabled for the account. Sets POSIX access permissions for the file
            owner, the file owning group, and others. Each class may be granted
            read, write, or execute permission.  The sticky bit is also supported.
            Both symbolic (rwxrw-rw-) and 4-digit octal notation (e.g. 0766) are
            supported.
        :keyword ~datetime.datetime if_modified_since:
            A DateTime value. Azure expects the date value passed in to be UTC.
            If timezone is included, any non-UTC datetimes will be converted to UTC.
            If a date is passed in without timezone info, it is assumed to be UTC.
            Specify this header to perform the operation only
            if the resource has been modified since the specified time.
        :keyword ~datetime.datetime if_unmodified_since:
            A DateTime value. Azure expects the date value passed in to be UTC.
            If timezone is included, any non-UTC datetimes will be converted to UTC.
            If a date is passed in without timezone info, it is assumed to be UTC.
            Specify this header to perform the operation only if
            the resource has not been modified since the specified date/time.
        :keyword str etag:
            An ETag value, or the wildcard character (*). Used to check if the resource has changed,
            and act according to the condition specified by the `match_condition` parameter.
        :keyword ~azure.core.MatchConditions match_condition:
            The match condition to use upon the etag.
        :keyword int timeout:
            The timeout parameter is expressed in seconds.
        :return: DataLakeDirectoryClient

        .. admonition:: Example:

            .. literalinclude:: ../samples/datalake_samples_file_system_async.py
                :start-after: [START create_directory_from_file_system]
                :end-before: [END create_directory_from_file_system]
                :language: python
                :dedent: 12
                :caption: Create directory in the file system.
        """
        directory_client = self.get_directory_client(directory)
        await directory_client.create_directory(metadata=metadata, **kwargs)
        return directory_client

    @distributed_trace_async
    async def delete_directory(self, directory,  # type: Union[DirectoryProperties, str]
                               **kwargs):
        # type: (...) -> DataLakeDirectoryClient
        """
        Marks the specified path for deletion.

        :param directory:
            The directory with which to interact. This can either be the name of the directory,
            or an instance of DirectoryProperties.
        :type directory: str or ~azure.storage.filedatalake.DirectoryProperties
        :keyword lease:
            Required if the file has an active lease. Value can be a LeaseClient object
            or the lease ID as a string.
        :paramtype lease: ~azure.storage.filedatalake.aio.DataLakeLeaseClient or str
        :keyword ~datetime.datetime if_modified_since:
            A DateTime value. Azure expects the date value passed in to be UTC.
            If timezone is included, any non-UTC datetimes will be converted to UTC.
            If a date is passed in without timezone info, it is assumed to be UTC.
            Specify this header to perform the operation only
            if the resource has been modified since the specified time.
        :keyword ~datetime.datetime if_unmodified_since:
            A DateTime value. Azure expects the date value passed in to be UTC.
            If timezone is included, any non-UTC datetimes will be converted to UTC.
            If a date is passed in without timezone info, it is assumed to be UTC.
            Specify this header to perform the operation only if
            the resource has not been modified since the specified date/time.
        :keyword str etag:
            An ETag value, or the wildcard character (*). Used to check if the resource has changed,
            and act according to the condition specified by the `match_condition` parameter.
        :keyword ~azure.core.MatchConditions match_condition:
            The match condition to use upon the etag.
        :keyword int timeout:
            The timeout parameter is expressed in seconds.
        :return: DataLakeDirectoryClient

        .. admonition:: Example:

            .. literalinclude:: ../samples/datalake_samples_file_system_async.py
                :start-after: [START delete_directory_from_file_system]
                :end-before: [END delete_directory_from_file_system]
                :language: python
                :dedent: 12
                :caption: Delete directory in the file system.
        """
        directory_client = self.get_directory_client(directory)
        await directory_client.delete_directory(**kwargs)
        return directory_client

    @distributed_trace_async
    async def create_file(self, file,  # type: Union[FileProperties, str]
                          **kwargs):
        # type: (...) -> DataLakeFileClient
        """
        Create file

        :param file:
            The file with which to interact. This can either be the name of the file,
            or an instance of FileProperties.
        :type file: str or ~azure.storage.filedatalake.FileProperties
        :param ~azure.storage.filedatalake.ContentSettings content_settings:
            ContentSettings object used to set path properties.
        :param metadata:
            Name-value pairs associated with the file as metadata.
        :type metadata: dict(str, str)
        :keyword lease:
            Required if the file has an active lease. Value can be a DataLakeLeaseClient object
            or the lease ID as a string.
        :paramtype lease: ~azure.storage.filedatalake.aio.DataLakeLeaseClient or str
        :keyword str umask:
            Optional and only valid if Hierarchical Namespace is enabled for the account.
            When creating a file or directory and the parent folder does not have a default ACL,
            the umask restricts the permissions of the file or directory to be created.
            The resulting permission is given by p & ^u, where p is the permission and u is the umask.
            For example, if p is 0777 and u is 0057, then the resulting permission is 0720.
            The default permission is 0777 for a directory and 0666 for a file. The default umask is 0027.
            The umask must be specified in 4-digit octal notation (e.g. 0766).
        :keyword str permissions:
            Optional and only valid if Hierarchical Namespace
            is enabled for the account. Sets POSIX access permissions for the file
            owner, the file owning group, and others. Each class may be granted
            read, write, or execute permission.  The sticky bit is also supported.
            Both symbolic (rwxrw-rw-) and 4-digit octal notation (e.g. 0766) are
            supported.
        :keyword ~datetime.datetime if_modified_since:
            A DateTime value. Azure expects the date value passed in to be UTC.
            If timezone is included, any non-UTC datetimes will be converted to UTC.
            If a date is passed in without timezone info, it is assumed to be UTC.
            Specify this header to perform the operation only
            if the resource has been modified since the specified time.
        :keyword ~datetime.datetime if_unmodified_since:
            A DateTime value. Azure expects the date value passed in to be UTC.
            If timezone is included, any non-UTC datetimes will be converted to UTC.
            If a date is passed in without timezone info, it is assumed to be UTC.
            Specify this header to perform the operation only if
            the resource has not been modified since the specified date/time.
        :keyword str etag:
            An ETag value, or the wildcard character (*). Used to check if the resource has changed,
            and act according to the condition specified by the `match_condition` parameter.
        :keyword ~azure.core.MatchConditions match_condition:
            The match condition to use upon the etag.
        :keyword int timeout:
            The timeout parameter is expressed in seconds.
        :return: DataLakeFileClient

        .. admonition:: Example:

            .. literalinclude:: ../samples/datalake_samples_file_system_async.py
                :start-after: [START create_file_from_file_system]
                :end-before: [END create_file_from_file_system]
                :language: python
                :dedent: 12
                :caption: Create file in the file system.
        """
        file_client = self.get_file_client(file)
        await file_client.create_file(**kwargs)
        return file_client

    @distributed_trace_async
    async def delete_file(self, file,  # type: Union[FileProperties, str]
                          **kwargs):
        # type: (...) -> DataLakeFileClient
        """
        Marks the specified file for deletion.

        :param file:
            The file with which to interact. This can either be the name of the file,
            or an instance of FileProperties.
        :type file: str or ~azure.storage.filedatalake.FileProperties
        :keyword lease:
            Required if the file has an active lease. Value can be a LeaseClient object
            or the lease ID as a string.
        :paramtype lease: ~azure.storage.filedatalake.aio.DataLakeLeaseClient or str
        :keyword ~datetime.datetime if_modified_since:
            A DateTime value. Azure expects the date value passed in to be UTC.
            If timezone is included, any non-UTC datetimes will be converted to UTC.
            If a date is passed in without timezone info, it is assumed to be UTC.
            Specify this header to perform the operation only
            if the resource has been modified since the specified time.
        :keyword ~datetime.datetime if_unmodified_since:
            A DateTime value. Azure expects the date value passed in to be UTC.
            If timezone is included, any non-UTC datetimes will be converted to UTC.
            If a date is passed in without timezone info, it is assumed to be UTC.
            Specify this header to perform the operation only if
            the resource has not been modified since the specified date/time.
        :keyword str etag:
            An ETag value, or the wildcard character (*). Used to check if the resource has changed,
            and act according to the condition specified by the `match_condition` parameter.
        :keyword ~azure.core.MatchConditions match_condition:
            The match condition to use upon the etag.
        :keyword int timeout:
            The timeout parameter is expressed in seconds.
        :return: DataLakeFileClient

        .. literalinclude:: ../samples/datalake_samples_file_system_async.py
            :start-after: [START delete_file_from_file_system]
            :end-before: [END delete_file_from_file_system]
            :language: python
            :dedent: 12
            :caption: Delete file in the file system.
        """
        file_client = self.get_file_client(file)
        await file_client.delete_file(**kwargs)
        return file_client

    # TODO: Temporarily removing this for GA release.
    # @distributed_trace_async
    # async def delete_files(self, *files, **kwargs):
    #     # type: (...) -> AsyncIterator[AsyncHttpResponse]
    #     """Marks the specified files or empty directories for deletion.

    #     The files/empty directories are later deleted during garbage collection.

    #     If a delete retention policy is enabled for the service, then this operation soft deletes the
    #     files/empty directories and retains the files or snapshots for specified number of days.
    #     After specified number of days, files' data is removed from the service during garbage collection.
    #     Soft deleted files/empty directories are accessible through :func:`list_deleted_paths()`.

    #     :param files:
    #         The files/empty directories to delete. This can be a single file/empty directory, or multiple values can
    #         be supplied, where each value is either the name of the file/directory (str) or
    #         FileProperties/DirectoryProperties.

    #         .. note::
    #             When the file/dir type is dict, here's a list of keys, value rules.

    #             blob name:
    #                 key: 'name', value type: str
    #             if the file modified or not:
    #                 key: 'if_modified_since', 'if_unmodified_since', value type: datetime
    #             etag:
    #                 key: 'etag', value type: str
    #             match the etag or not:
    #                 key: 'match_condition', value type: MatchConditions
    #             lease:
    #                 key: 'lease_id', value type: Union[str, LeaseClient]
    #             timeout for subrequest:
    #                 key: 'timeout', value type: int

    #     :type files: list[str], list[dict],
    #         or list[Union[~azure.storage.filedatalake.FileProperties, ~azure.storage.filedatalake.DirectoryProperties]
    #     :keyword ~datetime.datetime if_modified_since:
    #         A DateTime value. Azure expects the date value passed in to be UTC.
    #         If timezone is included, any non-UTC datetimes will be converted to UTC.
    #         If a date is passed in without timezone info, it is assumed to be UTC.
    #         Specify this header to perform the operation only
    #         if the resource has been modified since the specified time.
    #     :keyword ~datetime.datetime if_unmodified_since:
    #         A DateTime value. Azure expects the date value passed in to be UTC.
    #         If timezone is included, any non-UTC datetimes will be converted to UTC.
    #         If a date is passed in without timezone info, it is assumed to be UTC.
    #         Specify this header to perform the operation only if
    #         the resource has not been modified since the specified date/time.
    #     :keyword bool raise_on_any_failure:
    #         This is a boolean param which defaults to True. When this is set, an exception
    #         is raised even if there is a single operation failure.
    #     :keyword int timeout:
    #         The timeout parameter is expressed in seconds.
    #     :return: An iterator of responses, one for each blob in order
    #     :rtype: AsyncIterator[~azure.core.pipeline.transport.AsyncHttpResponse]

    #     .. admonition:: Example:

    #         .. literalinclude:: ../samples/datalake_samples_file_system_async.py
    #             :start-after: [START batch_delete_files_or_empty_directories]
    #             :end-before: [END batch_delete_files_or_empty_directories]
    #             :language: python
    #             :dedent: 4
    #             :caption: Deleting multiple files or empty directories.
    #     """
    #     return await self._container_client.delete_blobs(*files, **kwargs)

    @distributed_trace_async
    async def _undelete_path(self, deleted_path_name, deletion_id, **kwargs):
        # type: (str, str, **Any) -> Union[DataLakeDirectoryClient, DataLakeFileClient]
        """Restores soft-deleted path.

        Operation will only be successful if used within the specified number of days
        set in the delete retention policy.

        .. versionadded:: 12.4.0
            This operation was introduced in API version '2020-06-12'.

        :param str deleted_path_name:
            Specifies the name of the deleted container to restore.
        :param str deletion_id:
            Specifies the version of the deleted container to restore.
        :keyword int timeout:
            The timeout parameter is expressed in seconds.
        :rtype: ~azure.storage.file.datalake.aio.DataLakeDirectoryClient
                or azure.storage.file.datalake.aio.DataLakeFileClient
        """
        _, url, undelete_source = self._undelete_path_options(deleted_path_name, deletion_id)

        pipeline = AsyncPipeline(
            transport=AsyncTransportWrapper(self._pipeline._transport), # pylint: disable = protected-access
            policies=self._pipeline._impl_policies # pylint: disable = protected-access
        )
        path_client = AzureDataLakeStorageRESTAPI(
            url, filesystem=self.file_system_name, path=deleted_path_name, pipeline=pipeline)
        try:
            is_file = await path_client.path.undelete(undelete_source=undelete_source, cls=is_file_path, **kwargs)
            if is_file:
                return self.get_file_client(deleted_path_name)
            return self.get_directory_client(deleted_path_name)
        except HttpResponseError as error:
            process_storage_error(error)

    def _get_root_directory_client(self):
        # type: () -> DataLakeDirectoryClient
        """Get a client to interact with the root directory.

        :returns: A DataLakeDirectoryClient.
        :rtype: ~azure.storage.filedatalake.aio.DataLakeDirectoryClient
        """
        return self.get_directory_client('/')

    def get_directory_client(self, directory  # type: Union[DirectoryProperties, str]
                             ):
        # type: (...) -> DataLakeDirectoryClient
        """Get a client to interact with the specified directory.

        The directory need not already exist.

        :param directory:
            The directory with which to interact. This can either be the name of the directory,
            or an instance of DirectoryProperties.
        :type directory: str or ~azure.storage.filedatalake.DirectoryProperties
        :returns: A DataLakeDirectoryClient.
        :rtype: ~azure.storage.filedatalake.aio.DataLakeDirectoryClient

        .. admonition:: Example:

            .. literalinclude:: ../samples/datalake_samples_file_system_async.py
                :start-after: [START get_directory_client_from_file_system]
                :end-before: [END get_directory_client_from_file_system]
                :language: python
                :dedent: 12
                :caption: Getting the directory client to interact with a specific directory.
        """
        try:
            directory_name = directory.get('name')
        except AttributeError:
            directory_name = str(directory)
        _pipeline = AsyncPipeline(
            transport=AsyncTransportWrapper(self._pipeline._transport), # pylint: disable = protected-access
            policies=self._pipeline._impl_policies # pylint: disable = protected-access
        )
        return DataLakeDirectoryClient(self.url, self.file_system_name, directory_name=directory_name,
                                       credential=self._raw_credential,
                                       api_version=self.api_version,
                                       _configuration=self._config, _pipeline=_pipeline,
                                       _hosts=self._hosts,
                                       require_encryption=self.require_encryption,
                                       key_encryption_key=self.key_encryption_key,
                                       key_resolver_function=self.key_resolver_function,
                                       loop=self._loop
                                       )

    def get_file_client(self, file_path  # type: Union[FileProperties, str]
                        ):
        # type: (...) -> DataLakeFileClient
        """Get a client to interact with the specified file.

        The file need not already exist.

        :param file_path:
            The file with which to interact. This can either be the path of the file(from root directory),
            or an instance of FileProperties. eg. directory/subdirectory/file
        :type file_path: str or ~azure.storage.filedatalake.FileProperties
        :returns: A DataLakeFileClient.
        :rtype: ~azure.storage.filedatalake.aio.DataLakeFileClient

        .. admonition:: Example:

            .. literalinclude:: ../samples/datalake_samples_file_system_async.py
                :start-after: [START get_file_client_from_file_system]
                :end-before: [END get_file_client_from_file_system]
                :language: python
                :dedent: 12
                :caption: Getting the file client to interact with a specific file.
        """
        try:
            file_path = file_path.get('name')
        except AttributeError:
            file_path = str(file_path)
        _pipeline = AsyncPipeline(
            transport=AsyncTransportWrapper(self._pipeline._transport), # pylint: disable = protected-access
            policies=self._pipeline._impl_policies # pylint: disable = protected-access
        )
        return DataLakeFileClient(
            self.url, self.file_system_name, file_path=file_path, credential=self._raw_credential,
            api_version=self.api_version,
            _hosts=self._hosts, _configuration=self._config, _pipeline=_pipeline,
            require_encryption=self.require_encryption,
            key_encryption_key=self.key_encryption_key,
            key_resolver_function=self.key_resolver_function, loop=self._loop)

    @distributed_trace
    def list_deleted_paths(self, **kwargs):
        # type: (Any) -> AsyncItemPaged[DeletedPathProperties]
        """Returns a generator to list the deleted (file or directory) paths under the specified file system.
        The generator will lazily follow the continuation tokens returned by
        the service.

        .. versionadded:: 12.4.0
            This operation was introduced in API version '2020-06-12'.

        :keyword str path_prefix:
            Filters the results to return only paths under the specified path.
        :keyword int results_per_page:
            An optional value that specifies the maximum number of items to return per page.
            If omitted or greater than 5,000, the response will include up to 5,000 items per page.
        :keyword int timeout:
            The timeout parameter is expressed in seconds.
        :returns: An iterable (auto-paging) response of DeletedPathProperties.
        :rtype:
            ~azure.core.paging.AsyncItemPaged[~azure.storage.filedatalake.DeletedPathProperties]
        """
        path_prefix = kwargs.pop('path_prefix', None)
        timeout = kwargs.pop('timeout', None)
        results_per_page = kwargs.pop('results_per_page', None)
        command = functools.partial(
            self._datalake_client_for_blob_operation.file_system.list_blob_hierarchy_segment,
            showonly=ListBlobsIncludeItem.deleted,
            timeout=timeout,
            **kwargs)
        return AsyncItemPaged(
            command, prefix=path_prefix, page_iterator_class=DeletedPathPropertiesPaged,
            results_per_page=results_per_page, **kwargs)
