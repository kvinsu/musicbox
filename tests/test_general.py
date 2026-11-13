from unittest.mock import AsyncMock, MagicMock

import pytest
import requests

from cogs.general import General
from config.settings import Config


@pytest.fixture
def general() -> General:
    return General(MagicMock())


@pytest.fixture
def ctx() -> MagicMock:
    ctx = MagicMock()
    ctx.send = AsyncMock()
    ctx.author.mention = '@author'
    return ctx


def sent_embed(ctx):
    return ctx.send.await_args.kwargs['embed']


async def test_roulette_ignores_extra_whitespace(general, ctx, monkeypatch):
    monkeypatch.setattr(general.sys_random, 'choice', lambda options: options[-1])

    await general.roulette.callback(general, ctx, options=' a   b ')

    assert {f.name: f.value for f in sent_embed(ctx).fields} == {'Options': 'a, b', 'Selected': 'b'}


async def test_slap_mentions_reason_only_when_given(general, ctx):
    user = MagicMock(mention='@target')

    await general.slap.callback(general, ctx, user)
    assert sent_embed(ctx).description == '@author slapped @target.'

    await general.slap.callback(general, ctx, user, reason='for science')
    assert sent_embed(ctx).description == '@author slapped @target. Reason: for science'


async def test_gif_falls_back_without_token(general, monkeypatch):
    monkeypatch.setattr(Config, 'TENOR_TOKEN', None)
    monkeypatch.setattr(requests, 'get', MagicMock(side_effect=AssertionError('no request expected')))

    assert (await general.get_random_gif('cat')).startswith('https://c.tenor.com/')


async def test_gif_search_term_is_sent_as_query_param(general, monkeypatch):
    monkeypatch.setattr(Config, 'TENOR_TOKEN', 'key')
    response = MagicMock()
    response.json.return_value = {'results': [{'media': [{'gif': {'url': 'https://media/x.gif'}}]}]}
    get = MagicMock(return_value=response)
    monkeypatch.setattr(requests, 'get', get)

    assert await general.get_random_gif('cat & dog') == 'https://media/x.gif'
    assert get.call_args.kwargs['params']['q'] == 'cat & dog'


async def test_gif_falls_back_when_request_fails(general, monkeypatch):
    monkeypatch.setattr(Config, 'TENOR_TOKEN', 'key')
    monkeypatch.setattr(requests, 'get', MagicMock(side_effect=requests.Timeout()))

    assert (await general.get_random_gif('cat')).startswith('https://c.tenor.com/')
