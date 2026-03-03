##########################################################################################
#
# Script name: test_subscriptions.py
#
# Description: Tests subscription double opt-in and unsubscribe flow.
#
##########################################################################################

from urllib.parse import parse_qs, urlparse

from ai_news_feed import subscriptions


def _token_from_url(url: str) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    return (query.get('token') or [''])[0]


def test_subscription_confirm_and_unsubscribe(monkeypatch, tmp_path) -> None:
    db_path = str(tmp_path / 'subscribers.db')
    monkeypatch.setenv('SUBSCRIPTION_TOKEN_SECRET', 'unit-test-secret')
    monkeypatch.setattr(subscriptions, '_send_confirmation_email', lambda email, confirm_url: True)
    monkeypatch.setattr(subscriptions, '_send_subscribed_email', lambda email, unsubscribe_url: True)

    subscribe_result = subscriptions.subscribe_email(
        db_path=db_path,
        email='tester@example.com',
        source='site',
        public_base_url='https://newsletter.example.com',
    )
    assert subscribe_result.get('ok') is True
    assert subscribe_result.get('status') == 'pending_confirmation'
    confirm_token = _token_from_url(subscribe_result.get('confirm_url') or '')
    assert confirm_token

    confirm_result = subscriptions.confirm_subscription(
        db_path=db_path,
        token=confirm_token,
        public_base_url='https://newsletter.example.com',
    )
    assert confirm_result.get('ok') is True
    assert confirm_result.get('status') == 'active'
    unsubscribe_token = _token_from_url(confirm_result.get('unsubscribe_url') or '')
    assert unsubscribe_token

    unsubscribe_result = subscriptions.unsubscribe_subscription(
        db_path=db_path,
        token=unsubscribe_token,
    )
    assert unsubscribe_result.get('ok') is True
    assert unsubscribe_result.get('status') == 'unsubscribed'


def test_subscription_rejects_invalid_email(tmp_path) -> None:
    result = subscriptions.subscribe_email(
        db_path=str(tmp_path / 'subscribers.db'),
        email='not-an-email',
        source='site',
    )
    assert result.get('ok') is False
    assert result.get('error') == 'invalid_email'
