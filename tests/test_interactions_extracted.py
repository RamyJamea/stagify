import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock
import json
import httpx
from google import genai

from pydantic import BaseModel, ValidationError
from stagify.nlp.providers.gemini import GeminiNLP
from stagify.nlp.interface import ProviderError, ProviderOutputError, ProviderTransientError
from stagify.nlp.schemas import GenConfig, ToolSpec, ToolResult



class Step(BaseModel):
    type: str
    signature: str | None = None
    id: str | None = None
    name: str | None = None
    arguments: dict | None = None


class ProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_plain_text_input_returns_a_complete_turn(self):
        create = AsyncMock(return_value=SimpleNamespace(
            id='text', status='completed', output_text='Prioritize repeat customers.',
            usage=None, steps=[Step(type='text')]))
        provider = GeminiNLP()
        provider.client = SimpleNamespace(aio=SimpleNamespace(interactions=SimpleNamespace(create=create)))
        result = await provider.gen_turn(GenConfig(model_name='gemini-3.1-flash-lite'), 'Summarize')
        self.assertEqual(result.text, 'Prioritize repeat customers.')
        self.assertEqual(result.status, 'completed')
        self.assertEqual(result.calls, [])
        self.assertEqual(create.call_args.kwargs['input'], 'Summarize')
        self.assertFalse(create.call_args.kwargs['stream'])
        self.assertFalse(create.call_args.kwargs['store'])

    async def test_complete_turn_replays_all_steps_and_disables_stream_store_retries(self):
        provider = GeminiNLP()
        await provider.connect('dummy')
        actual_client = provider.client
        create = AsyncMock(return_value=SimpleNamespace(
            id='request', status='requires_action', output_text='', usage=None,
            steps=[Step(type='thought', signature='opaque'),
                   Step(type='function_call', id='a', name='test', arguments={'x': 1}),
                   Step(type='function_call', id='b', name='test', arguments={'x': 2})]))
        provider.client = SimpleNamespace(aio=SimpleNamespace(interactions=SimpleNamespace(create=create)))
        response = await provider.gen_turn(GenConfig(model_name='gemini-2.5-flash'), [], [ToolSpec(name='test', description='test', parameters={})])
        self.assertEqual(len(response.calls), 2)
        self.assertEqual(response.replay_content[0]['signature'], 'opaque')
        self.assertFalse(create.call_args.kwargs['stream'])
        self.assertFalse(create.call_args.kwargs['store'])
        self.assertEqual(provider.create_tool_result(ToolResult(name='test', call_id='a', result={'ok': True}))[0]['result'][0]['type'], 'text')
        provider.client = actual_client
        await provider.disconnect()
        self.assertIsNone(provider.client)

    async def test_generation_schema_validates_parameter_ranges(self):
        for values in [
            {'model_name': ''},
            {'model_name': 'gemini-3.8-flash', 'thinking_level': 'unsupported'},
            {'model_name': 'gemini-3.8-flash', 'temperature': -1},
            {'model_name': 'gemini-3.8-flash', 'temperature': 3},
            {'model_name': 'gemini-3.8-flash', 'top_p': 0},
            {'model_name': 'gemini-3.8-flash', 'top_p': 2},
            {'model_name': 'gemini-3.8-flash', 'max_output_tokens': 0},
        ]:
            with self.subTest(values=values), self.assertRaises(ValidationError):
                GenConfig(**values)
        config = GenConfig(model_name='gemini-3.8-flash', thinking_level='medium')
        self.assertEqual(GenConfig(model_name='custom-model').model_name, 'custom-model')
        with self.assertRaises(ValidationError):
            config.top_p = 2

    async def test_real_sdk_serialization_with_mock_http(self):
        captured = []
        def transport(request):
            captured.append(json.loads(request.content))
            return httpx.Response(200, json={
                'id': 'req', 'status': 'requires_action', 'model': 'gemini-2.5-flash',
                'steps': [{'type': 'thought', 'signature': 'opaque'},
                          {'type': 'function_call', 'id': 'call', 'name': 'complete_stage', 'arguments': {'x': 1}}]})
        http_client = httpx.AsyncClient(transport=httpx.MockTransport(transport))
        provider = GeminiNLP()
        provider.client = genai.Client(api_key='dummy', http_options={'httpx_async_client': http_client, 'retry_options': {'attempts': 0}})
        response = await provider.gen_turn(GenConfig(model_name='gemini-2.5-flash'), [provider.create_user_msg('test')],
                                          [ToolSpec(name="complete_stage", description='test', parameters={'type': 'object', 'properties': {'x': {'type': 'integer'}}})])
        self.assertEqual(response.calls[0].arguments, {'x': 1})
        self.assertFalse(captured[0]['store'])
        self.assertEqual(captured[0]['tools'][0]['name'], 'complete_stage')
        self.assertEqual(response.replay_content[0]['signature'], 'opaque')
        await provider.disconnect()
        await http_client.aclose()

    async def test_missing_generation_steps_fail_with_an_output_error(self):
        for missing_steps in ({}, {"steps": None}):
            with self.subTest(missing_steps=missing_steps):
                captured = []

                def transport(request):
                    captured.append(request)
                    return httpx.Response(200, json={
                        "id": "empty", "status": "completed", **missing_steps,
                    })

                http_client = httpx.AsyncClient(transport=httpx.MockTransport(transport))
                provider = GeminiNLP()
                provider.client = genai.Client(api_key="dummy", http_options={
                    "httpx_async_client": http_client, "retry_options": {"attempts": 0},
                })
                try:
                    with self.assertRaisesRegex(ProviderOutputError, "no generation steps"):
                        await provider.gen_turn(GenConfig(model_name="offline"), [])
                    self.assertEqual(len(captured), 1)
                finally:
                    await provider.disconnect()
                    await http_client.aclose()

    async def test_malformed_tool_json_has_a_specific_output_error(self):
        error_code = 'malformed_tool_call'
        def transport(request):
            return httpx.Response(400, json={'error': {'code': error_code, 'message': 'Invalid output'}})
        http_client = httpx.AsyncClient(transport=httpx.MockTransport(transport))
        provider = GeminiNLP()
        provider.client = genai.Client(api_key='dummy', http_options={'httpx_async_client': http_client, 'retry_options': {'attempts': 0}})
        try:
            with self.assertRaises(ProviderOutputError):
                await provider.gen_turn(GenConfig(model_name='gemini-3.1-flash-lite'), [])
            error_code = 'invalid_request'
            with self.assertRaises(ProviderError) as failure:
                await provider.gen_turn(GenConfig(model_name='gemini-3.1-flash-lite'), [])
            self.assertNotIsInstance(failure.exception, ProviderOutputError)
            self.assertNotIsInstance(failure.exception, ProviderTransientError)
            self.assertEqual(failure.exception.status_code, 400)
        finally:
            await provider.disconnect()
            await http_client.aclose()

    async def test_retry_after_and_http_error_classification(self):
        def transport(request):
            headers = {} if retry_after is None else {'Retry-After': retry_after}
            return httpx.Response(status, headers=headers, json={'error': {'code': 'request_failed'}})

        http_client = httpx.AsyncClient(transport=httpx.MockTransport(transport))
        provider = GeminiNLP()
        provider.client = genai.Client(api_key='dummy', http_options={'httpx_async_client': http_client})
        try:
            for status, retry_after, expected in [
                (408, '3', 3), (429, '3', 3), (500, None, None), (502, '-2', 0),
                (503, 'invalid', None), (504, 'inf', None),
                (503, 'Wed, 01 Jan 2020 00:00:00 GMT', 0),
            ]:
                with self.subTest(status=status, retry_after=retry_after):
                    with self.assertRaises(ProviderTransientError) as failure:
                        await provider.gen_turn(GenConfig(model_name='gemini-3.1-flash-lite'), [])
                    self.assertEqual(failure.exception.status_code, status)
                    self.assertEqual(failure.exception.retry_after, expected)
                    self.assertIsInstance(failure.exception, ProviderError)
            for status in (400, 401, 403, 404, 422):
                with self.subTest(status=status), self.assertRaises(ProviderError) as failure:
                    await provider.gen_turn(GenConfig(model_name='gemini-3.1-flash-lite'), [])
                self.assertNotIsInstance(failure.exception, (ProviderTransientError, ProviderOutputError))
                self.assertEqual(failure.exception.status_code, status)
        finally:
            await provider.disconnect()
            await http_client.aclose()

    async def test_structured_retry_delay_and_explicit_daily_quota(self):
        payload = {'code': 'rate_limit_exceeded', 'details': [
            {'@type': 'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': '34.4s'},
        ]}
        headers = {}
        def transport(request):
            return httpx.Response(429, headers=headers, json={'error': payload})
        http_client = httpx.AsyncClient(transport=httpx.MockTransport(transport))
        provider = GeminiNLP()
        provider.client = genai.Client(api_key='dummy', http_options={'httpx_async_client': http_client})
        try:
            for header, expected in ((None, 34.4), ('50', 50), ('invalid', 34.4)):
                headers = {} if header is None else {'Retry-After': header}
                with self.subTest(header=header), self.assertRaises(ProviderTransientError) as failure:
                    await provider.gen_turn(GenConfig(model_name='offline'), [])
                self.assertEqual(failure.exception.retry_after, expected)
            payload = {'code': 'quota_exceeded'}
            with self.assertRaises(ProviderError) as failure:
                await provider.gen_turn(GenConfig(model_name='offline'), [])
            self.assertNotIsInstance(failure.exception, ProviderTransientError)
            self.assertEqual(failure.exception.status_code, 429)
        finally:
            await provider.disconnect()
            await http_client.aclose()

    async def test_sdk_transport_errors_are_transient_without_hidden_retries(self):
        for error in (httpx.ConnectError('connection-secret'), httpx.ReadTimeout('timeout-secret')):
            captured = []
            def transport(request):
                captured.append(request)
                raise error
            http_client = httpx.AsyncClient(transport=httpx.MockTransport(transport))
            provider = GeminiNLP()
            provider.client = genai.Client(api_key='dummy', http_options={'httpx_async_client': http_client})
            try:
                with self.subTest(error=type(error).__name__), self.assertRaises(ProviderTransientError) as failure:
                    await provider.gen_turn(GenConfig(model_name='offline'), [])
                self.assertEqual(len(captured), 1)
                self.assertIsNone(failure.exception.status_code)
                self.assertNotIn('secret', str(failure.exception))
            finally:
                await provider.disconnect()
                await http_client.aclose()

    async def test_malformed_error_body_does_not_mask_http_status(self):
        class BadRequest(Exception):
            status_code = 400

        for body in (None, 'not-json', [], {'error': None}, {'error': []}):
            error = BadRequest('provider-secret')
            error.body = body
            provider = GeminiNLP()
            create = AsyncMock(side_effect=error)
            provider.client = SimpleNamespace(aio=SimpleNamespace(interactions=SimpleNamespace(create=create)))
            with self.subTest(body=body), self.assertRaises(ProviderError) as failure:
                await provider.gen_turn(GenConfig(model_name='offline'), [])
            self.assertEqual(failure.exception.status_code, 400)
            self.assertNotIn('provider-secret', str(failure.exception))

    async def test_unexpected_exception_is_not_masked_by_http_error_handling(self):
        error = ValueError('SDK configuration failure')
        provider = GeminiNLP()
        provider.client = SimpleNamespace(aio=SimpleNamespace(interactions=SimpleNamespace(create=AsyncMock(side_effect=error))))
        with self.assertRaises(ValueError) as failure:
            await provider.gen_turn(GenConfig(model_name='gemini-3.1-flash-lite'), [])
        self.assertIs(failure.exception, error)

    async def test_temporary_http_failure_is_classified_without_sdk_retry(self):
        captured = []
        def transport(request):
            captured.append(request)
            return httpx.Response(503, json={'error': {'code': 'service_unavailable', 'message': 'High demand'}})
        http_client = httpx.AsyncClient(transport=httpx.MockTransport(transport))
        provider = GeminiNLP()
        provider.client = genai.Client(api_key='dummy', http_options={'httpx_async_client': http_client, 'retry_options': {'attempts': 0}})
        try:
            with self.assertRaises(ProviderTransientError) as failure:
                await provider.gen_turn(GenConfig(model_name='gemini-3.8-flash'), [])
            self.assertEqual(failure.exception.status_code, 503)
            self.assertEqual(len(captured), 1, [str(r.url) for r in captured])
        finally:
            await provider.disconnect()
            await http_client.aclose()
