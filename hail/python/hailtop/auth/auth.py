from typing import Optional
import os
import aiohttp
from hailtop.config import get_deploy_config, DeployConfig
from hailtop.utils import async_to_blocking, request_retry_transient_errors
from hailtop.tls import get_context_specific_ssl_client_session

from .tokens import get_tokens


async def async_delete_session(session_id: str):
    # only works for developers creation sessions for service accounts
    deploy_config = get_deploy_config()
    headers = service_auth_headers(deploy_config, 'auth')
    url = deploy_config.url('auth', '/api/v1alpha/delete_session')
    async with get_context_specific_ssl_client_session(
            raise_for_status=True, timeout=aiohttp.ClientTimeout(total=5)) as session:
        resp = await request_retry_transient_errors(
            session, 'POST', url, headers=headers, json={
                'session_id': session_id
            })
        return await resp.json()


def delete_session(username: str):
    return async_to_blocking(async_delete_session(username))


async def async_create_session(username: str, max_age_secs: Optional[int] = None):
    # only works for developers creation sessions for service accounts
    deploy_config = get_deploy_config()
    headers = service_auth_headers(deploy_config, 'auth')
    url = deploy_config.url('auth', '/api/v1alpha/create_session')
    async with get_context_specific_ssl_client_session(
            raise_for_status=True, timeout=aiohttp.ClientTimeout(total=5)) as session:
        resp = await request_retry_transient_errors(
            session, 'POST', url, headers=headers, json={
                'username': username,
                'max_age_secs': max_age_secs
            })
        return await resp.json()


def create_session(username: str, max_age_secs: Optional[int] = None):
    return async_to_blocking(async_create_session(username, max_age_secs))


async def async_delete_user(username: str):
    deploy_config = get_deploy_config()
    headers = service_auth_headers(deploy_config, 'auth')
    url = deploy_config.url('auth', '/api/v1alpha/users/delete')
    async with get_context_specific_ssl_client_session(
            raise_for_status=True, timeout=aiohttp.ClientTimeout(total=5)) as session:
        resp = await request_retry_transient_errors(
            session, 'POST', url, headers=headers, json={
                'username': username
            })
        return await resp.json()


def delete_user(username: str):
    return async_to_blocking(async_delete_user(username))


async def async_create_user(username: str,
                            email: Optional[str],
                            *,
                            is_developer: bool = False,
                            is_service_account: bool = False):
    deploy_config = get_deploy_config()
    headers = service_auth_headers(deploy_config, 'auth')
    url = deploy_config.url('auth', '/api/v1alpha/users')
    async with get_context_specific_ssl_client_session(
            raise_for_status=True, timeout=aiohttp.ClientTimeout(total=5)) as session:
        resp = await request_retry_transient_errors(
            session, 'POST', url, headers=headers, json={
                'username': username,
                'email': email,
                'is_developer': is_developer,
                'is_service_account': is_service_account
            })
        return await resp.json()


def create_user(username: str,
                email: Optional[str],
                is_developer: bool = False,
                is_service_account: bool = False):
    return async_to_blocking(async_create_user(
        username, email, is_developer=is_developer, is_service_account=is_service_account))


async def async_get_userinfo(*,
                             deploy_config: Optional[DeployConfig] = None,
                             session_id: Optional[str] = None,
                             client_session=None):
    if deploy_config is None:
        deploy_config = get_deploy_config()
    if client_session is None:
        client_session = get_context_specific_ssl_client_session(
            raise_for_status=True, timeout=aiohttp.ClientTimeout(total=5))

    if session_id is None:
        headers = service_auth_headers(deploy_config, 'auth')
    else:
        headers = {'Authorization': f'Bearer {session_id}'}

    userinfo_url = deploy_config.url('auth', '/api/v1alpha/userinfo')
    async with client_session as session:
        try:
            resp = await request_retry_transient_errors(
                session, 'GET', userinfo_url, headers=headers)
            return await resp.json()
        except aiohttp.client_exceptions.ClientResponseError as err:
            if err.status == 401:
                return None
            raise


def get_userinfo(deploy_config: Optional[DeployConfig] = None,
                 session_id: Optional[str] = None):
    return async_to_blocking(async_get_userinfo(deploy_config=deploy_config, session_id=session_id))


def namespace_auth_headers(deploy_config, ns, authorize_target=True, *, token_file=None):
    tokens = get_tokens(token_file)
    headers = {}
    if authorize_target:
        headers['Authorization'] = f'Bearer {tokens.namespace_token_or_error(ns)}'
    if deploy_config.location() == 'external' and ns != 'default':
        headers['X-Hail-Internal-Authorization'] = f'Bearer {tokens.namespace_token_or_error("default")}'
    return headers


def service_auth_headers(deploy_config, service, authorize_target=True, *, token_file=None):
    ns = deploy_config.service_ns(service)
    return namespace_auth_headers(deploy_config, ns, authorize_target, token_file=token_file)


def copy_paste_login(copy_paste_token, namespace=None):
    return async_to_blocking(async_copy_paste_login(copy_paste_token, namespace))


async def async_copy_paste_login(copy_paste_token, namespace=None):
    deploy_config = get_deploy_config()
    if namespace is not None:
        auth_ns = namespace
        deploy_config = deploy_config.with_service('auth', auth_ns)
    else:
        auth_ns = deploy_config.service_ns('auth')
    headers = namespace_auth_headers(deploy_config, auth_ns, authorize_target=False)

    async with aiohttp.ClientSession(
            raise_for_status=True,
            timeout=aiohttp.ClientTimeout(total=60),
            headers=headers) as session:
        resp = await request_retry_transient_errors(
            session, 'POST', deploy_config.url('auth', '/api/v1alpha/copy-paste-login'),
            params={'copy_paste_token': copy_paste_token})
        resp = await resp.json()
    token = resp['token']
    username = resp['username']

    tokens = get_tokens()
    tokens[auth_ns] = token
    dot_hail_dir = os.path.expanduser('~/.hail')
    if not os.path.exists(dot_hail_dir):
        os.mkdir(dot_hail_dir, mode=0o700)
    tokens.write()

    return auth_ns, username