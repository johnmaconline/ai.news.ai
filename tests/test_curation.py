##########################################################################################
#
# Script name: test_curation.py
#
# Description: Basic curation behavior tests.
#
##########################################################################################

from datetime import datetime, timezone

from ai_news_feed.curation import curate_sections, dedupe_articles, score_articles
from ai_news_feed.fetchers import build_sample_articles
from ai_news_feed.models import Article


def test_curate_sections_hits_minimums() -> None:
    articles = build_sample_articles()
    sections = curate_sections(
        articles=articles,
        min_per_section=3,
        max_per_section=5,
        feed_dt=datetime.now(timezone.utc),
        enable_llm_curation=False,
    )
    for section_slug, picks in sections.items():
        assert section_slug
        assert len(picks) >= 3
        assert len(picks) <= 5


def test_curate_sections_filters_items_older_than_24_hours() -> None:
    feed_dt = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
    old_article = Article(
        id='old-item',
        title='Old but high score announcement',
        url='https://example.com/old',
        summary='partnership launch funding and valuation',
        source_name='Example',
        source_type='rss',
        domain='example.com',
        published_at=datetime(2026, 2, 27, 10, 0, tzinfo=timezone.utc),
        priority=10.0,
        section_hint='practical-prompts',
    )
    fresh_article = Article(
        id='fresh-item',
        title='Fresh workflow update',
        url='https://example.com/fresh',
        summary='automation workflow for small business operations',
        source_name='Example',
        source_type='rss',
        domain='example.com',
        published_at=datetime(2026, 3, 1, 8, 0, tzinfo=timezone.utc),
        priority=5.0,
        section_hint='business',
    )
    sections = curate_sections(
        articles=[old_article, fresh_article],
        min_per_section=1,
        max_per_section=3,
        feed_dt=feed_dt,
        enable_llm_curation=False,
    )
    all_ids = {item.id for picks in sections.values() for item in picks}
    assert 'old-item' not in all_ids
    assert 'fresh-item' in all_ids


def test_high_signal_release_uses_extended_recency_grace() -> None:
    feed_dt = datetime(2026, 3, 6, 11, 0, tzinfo=timezone.utc)
    high_signal = Article(
        id='gpt-54-release',
        title='Introducing GPT-5.4',
        url='https://openai.com/index/introducing-gpt-5-4',
        summary='OpenAI released GPT-5.4 with stronger coding and computer use.',
        source_name='OpenAI News',
        source_type='rss',
        domain='openai.com',
        published_at=datetime(2026, 3, 5, 10, 0, tzinfo=timezone.utc),
        priority=9.0,
        section_hint='practical-prompts',
    )
    filler = Article(
        id='fresh-filler',
        title='Workflow notes',
        url='https://example.com/workflow-notes',
        summary='practical workflow tutorial for engineering teams',
        source_name='Example',
        source_type='rss',
        domain='example.com',
        published_at=datetime(2026, 3, 6, 9, 0, tzinfo=timezone.utc),
        priority=4.0,
        section_hint='engineering',
    )
    sections = curate_sections(
        articles=[high_signal, filler],
        min_per_section=1,
        max_per_section=3,
        feed_dt=feed_dt,
        enable_llm_curation=False,
    )
    all_ids = {item.id for picks in sections.values() for item in picks}
    assert 'gpt-54-release' in all_ids
    assert high_signal.metrics.get('recency_grace_applied') == 1.0


def test_high_signal_release_is_filtered_when_older_than_grace_window() -> None:
    feed_dt = datetime(2026, 3, 6, 11, 0, tzinfo=timezone.utc)
    too_old = Article(
        id='gpt-54-too-old',
        title='Introducing GPT-5.4',
        url='https://openai.com/index/introducing-gpt-5-4',
        summary='OpenAI released GPT-5.4 with stronger coding and computer use.',
        source_name='OpenAI News',
        source_type='rss',
        domain='openai.com',
        published_at=datetime(2026, 3, 4, 9, 0, tzinfo=timezone.utc),
        priority=9.0,
        section_hint='practical-prompts',
    )
    fresh = Article(
        id='fresh-for-check',
        title='Prompt template for test generation',
        url='https://example.com/prompts',
        summary='prompt template for unit test and ci pipeline automation',
        source_name='Example',
        source_type='rss',
        domain='example.com',
        published_at=datetime(2026, 3, 6, 10, 0, tzinfo=timezone.utc),
        priority=5.0,
        section_hint='practical-prompts',
    )
    sections = curate_sections(
        articles=[too_old, fresh],
        min_per_section=1,
        max_per_section=3,
        feed_dt=feed_dt,
        enable_llm_curation=False,
    )
    all_ids = {item.id for picks in sections.values() for item in picks}
    assert 'gpt-54-too-old' not in all_ids
    assert 'fresh-for-check' in all_ids


def test_business_prefers_practical_over_announcement_items() -> None:
    feed_dt = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
    announcement = Article(
        id='announce',
        title='OpenAI and Amazon announce strategic partnership',
        url='https://openai.com/index/partnership',
        summary='announcing partnership funding valuation and launch details',
        source_name='OpenAI News',
        source_type='rss',
        domain='openai.com',
        published_at=datetime(2026, 3, 1, 9, 0, tzinfo=timezone.utc),
        priority=8.0,
        section_hint='practical-prompts',
    )
    practical = Article(
        id='practical',
        title='How a solo founder uses AI workflows for a side hustle',
        url='https://example.com/side-hustle',
        summary='solopreneur automation workflow for customer support and operations',
        source_name='Indie Example',
        source_type='rss',
        domain='example.com',
        published_at=datetime(2026, 3, 1, 9, 30, tzinfo=timezone.utc),
        priority=6.0,
        section_hint='business',
    )
    articles = [announcement, practical]
    score_articles(articles, feed_dt=feed_dt)
    assert practical.scores['business'] > announcement.scores['business']


def test_practical_prompts_prefers_prompt_content_over_announcement_news() -> None:
    feed_dt = datetime(2026, 3, 3, 13, 0, tzinfo=timezone.utc)
    prompt_article = Article(
        id='prompt-playbook',
        title='Prompt template for generating robust unit tests in Python',
        url='https://example.com/prompt-playbook',
        summary='Prompt pattern with examples for test generation, code review checks, and CI validation.',
        source_name='Engineering Blog',
        source_type='rss',
        domain='example.com',
        published_at=datetime(2026, 3, 3, 10, 0, tzinfo=timezone.utc),
        priority=7.0,
        section_hint='practical-prompts',
    )
    announcement_article = Article(
        id='layoff-news',
        title='Company announces layoffs tied to AI investment',
        url='https://news.example.com/layoffs',
        summary='Funding round and restructuring announced by leadership.',
        source_name='News Site',
        source_type='rss',
        domain='news.example.com',
        published_at=datetime(2026, 3, 3, 9, 30, tzinfo=timezone.utc),
        priority=7.0,
        section_hint='practical-prompts',
    )
    score_articles([prompt_article, announcement_article], feed_dt=feed_dt)
    assert prompt_article.scores['practical-prompts'] > announcement_article.scores['practical-prompts']


def test_practical_prompts_excludes_generic_tool_roundups() -> None:
    feed_dt = datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc)
    roundup_article = Article(
        id='open-webui-roundup',
        title='11 Best Open WebUI Alternatives for Enterprise LLM Chat (2026)',
        url='https://dev.to/example/open-webui-alternatives',
        summary='Open WebUI alternatives for enterprise LLM chat and on-prem deployments.',
        source_name='DEV.to',
        source_type='rss',
        domain='dev.to',
        published_at=datetime(2026, 3, 10, 9, 30, tzinfo=timezone.utc),
        priority=7.0,
        section_hint='practical-prompts',
    )
    sections = curate_sections(
        articles=[roundup_article],
        min_per_section=1,
        max_per_section=3,
        feed_dt=feed_dt,
        enable_llm_curation=False,
    )
    practical_prompt_ids = {item.id for item in sections['practical-prompts']}
    assert 'open-webui-roundup' not in practical_prompt_ids


def test_practical_prompts_accepts_agent_md_and_prompt_files() -> None:
    feed_dt = datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc)
    agent_md_article = Article(
        id='agent-md-guide',
        title='Agents.md prompt pack for code review and CI checks',
        url='https://example.com/agents-md-guide',
        summary='Includes agents.md, system prompt examples, and CI prompt templates for code review workflows.',
        source_name='Example',
        source_type='rss',
        domain='example.com',
        published_at=datetime(2026, 3, 10, 10, 0, tzinfo=timezone.utc),
        priority=7.0,
        section_hint='practical-prompts',
    )
    sections = curate_sections(
        articles=[agent_md_article],
        min_per_section=1,
        max_per_section=3,
        feed_dt=feed_dt,
        enable_llm_curation=False,
    )
    practical_prompt_ids = {item.id for item in sections['practical-prompts']}
    assert 'agent-md-guide' in practical_prompt_ids


def test_for_fun_excludes_startup_funding_news() -> None:
    feed_dt = datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc)
    startup_article = Article(
        id='ami-labs-funding',
        title='Yann LeCun unveils his new startup Advanced Machine Intelligence (AMI Labs) -- and raises $1.03B',
        url='https://reddit.com/r/singularity/ami-labs',
        summary='Yann LeCun unveils AMI Labs with $1.03B in funding to build world models via JEPA.',
        source_name='r/singularity',
        source_type='reddit',
        domain='reddit.com',
        published_at=datetime(2026, 3, 10, 8, 31, tzinfo=timezone.utc),
        priority=7.0,
        section_hint='for-fun',
    )
    sections = curate_sections(
        articles=[startup_article],
        min_per_section=1,
        max_per_section=3,
        feed_dt=feed_dt,
        enable_llm_curation=False,
    )
    fun_ids = {item.id for item in sections['for-fun']}
    assert 'ami-labs-funding' not in fun_ids


def test_for_fun_accepts_playful_personal_projects() -> None:
    feed_dt = datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc)
    playful_article = Article(
        id='rpi-home-assistant',
        title='Weekend Raspberry Pi home automation workflow with a voice agent',
        url='https://example.com/rpi-home-assistant',
        summary='A weekend project using Raspberry Pi, Home Assistant, and a playful voice agent for smart home control.',
        source_name='Example',
        source_type='rss',
        domain='example.com',
        published_at=datetime(2026, 3, 10, 9, 0, tzinfo=timezone.utc),
        priority=6.0,
        section_hint='for-fun',
    )
    sections = curate_sections(
        articles=[playful_article],
        min_per_section=1,
        max_per_section=3,
        feed_dt=feed_dt,
        enable_llm_curation=False,
    )
    fun_ids = {item.id for item in sections['for-fun']}
    assert 'rpi-home-assistant' in fun_ids


def test_under_the_radar_prefers_smaller_social_accounts() -> None:
    feed_dt = datetime(2026, 3, 3, 13, 0, tzinfo=timezone.utc)
    small_account = Article(
        id='small-social',
        title='I built an AI test workflow in one weekend',
        url='https://x.com/smallbuilder/status/1',
        summary='Workflow notes and lessons learned for shipping faster.',
        source_name='X @smallbuilder',
        source_type='x',
        domain='x.com',
        published_at=datetime(2026, 3, 3, 10, 0, tzinfo=timezone.utc),
        priority=6.0,
        section_hint='under-the-radar',
        metrics={'followers': 5500, 'verified': 0.0, 'points': 30.0, 'comments': 12.0},
    )
    large_account = Article(
        id='large-social',
        title='I built an AI test workflow in one weekend',
        url='https://x.com/bigaccount/status/2',
        summary='Workflow notes and lessons learned for shipping faster.',
        source_name='X @bigaccount',
        source_type='x',
        domain='x.com',
        published_at=datetime(2026, 3, 3, 10, 0, tzinfo=timezone.utc),
        priority=6.0,
        section_hint='under-the-radar',
        metrics={'followers': 2200000, 'verified': 1.0, 'points': 30.0, 'comments': 12.0},
    )
    score_articles([small_account, large_account], feed_dt=feed_dt)
    assert small_account.scores['under-the-radar'] > large_account.scores['under-the-radar']


def test_curator_watchlist_boost_improves_section_score() -> None:
    feed_dt = datetime(2026, 3, 3, 13, 0, tzinfo=timezone.utc)
    curated = Article(
        id='curated-item',
        title='Agent workflow implementation guide',
        url='https://example.com/curated',
        summary='Practical coding agent workflow tutorial and implementation details.',
        source_name='Curator Source',
        source_type='rss',
        domain='example.com',
        published_at=datetime(2026, 3, 3, 10, 0, tzinfo=timezone.utc),
        priority=6.0,
        section_hint='business',
        tags={'business', 'curators'},
    )
    non_curated = Article(
        id='non-curated-item',
        title='Agent workflow implementation guide',
        url='https://example.org/non-curated',
        summary='Practical coding agent workflow tutorial and implementation details.',
        source_name='Regular Source',
        source_type='rss',
        domain='example.org',
        published_at=datetime(2026, 3, 3, 10, 0, tzinfo=timezone.utc),
        priority=6.0,
        section_hint='business',
        tags={'business'},
    )
    score_articles([curated, non_curated], feed_dt=feed_dt)
    assert curated.scores['business'] > non_curated.scores['business']


def test_curator_watchlist_sampling_is_capped(monkeypatch) -> None:
    feed_dt = datetime(2026, 3, 3, 13, 0, tzinfo=timezone.utc)
    monkeypatch.setenv('CURATOR_WATCHLIST_ENABLED', '1')
    monkeypatch.setenv('CURATOR_WATCHLIST_PER_SECTION_CAP', '1')
    monkeypatch.setenv('CURATOR_WATCHLIST_MAX_TOTAL', '2')
    monkeypatch.setenv('CURATOR_WATCHLIST_SCORE_BOOST', '2.0')

    articles: list[Article] = []
    for index in range(1, 7):
        articles.append(
            Article(
                id=f'curator-{index}',
                title=f'Curator workflow playbook {index}',
                url=f'https://curator{index}.example.com/post',
                summary='agent workflow tutorial implementation coding agent playbook',
                source_name=f'Curator {index}',
                source_type='rss',
                domain=f'curator{index}.example.com',
                published_at=datetime(2026, 3, 3, 11, 0, tzinfo=timezone.utc),
                priority=6.0,
                section_hint='business',
                tags={'curators', 'business'},
            )
        )
    for index in range(1, 7):
        articles.append(
            Article(
                id=f'regular-{index}',
                title=f'Regular workflow post {index}',
                url=f'https://regular{index}.example.com/post',
                summary='agent workflow tutorial implementation coding agent playbook',
                source_name=f'Regular {index}',
                source_type='rss',
                domain=f'regular{index}.example.com',
                published_at=datetime(2026, 3, 3, 11, 0, tzinfo=timezone.utc),
                priority=6.0,
                section_hint='business',
                tags={'business'},
            )
        )

    sections = curate_sections(
        articles=articles,
        min_per_section=1,
        max_per_section=2,
        feed_dt=feed_dt,
        enable_llm_curation=False,
    )
    curated_count = sum(
        1
        for picks in sections.values()
        for item in picks
        if 'curators' in {tag.lower() for tag in item.tags}
    )
    assert curated_count <= 2


def test_dedupe_articles_collects_corroborating_links() -> None:
    first = Article(
        id='a1',
        title='Agent workflow teardown with concrete code',
        url='https://example.com/post-a',
        summary='A detailed workflow and implementation walk-through.',
        source_name='Example One',
        source_type='rss',
        domain='example.com',
        published_at=datetime(2026, 3, 4, 11, 0, tzinfo=timezone.utc),
        priority=6.0,
    )
    second = Article(
        id='a2',
        title='Agent workflow teardown with concrete code',
        url='https://another.example/post-b',
        summary='A detailed workflow and implementation walk-through.',
        source_name='Example Two',
        source_type='rss',
        domain='another.example',
        published_at=datetime(2026, 3, 4, 11, 10, tzinfo=timezone.utc),
        priority=6.2,
    )
    deduped = dedupe_articles([first, second])
    assert len(deduped) == 2
    assert deduped[0].corroborating_urls or deduped[1].corroborating_urls
    cluster_sizes = [item.metrics.get('duplicate_cluster_size', 1.0) for item in deduped]
    assert max(cluster_sizes) >= 2.0


def test_score_articles_populates_provenance_and_confidence_fields() -> None:
    article = Article(
        id='prov-1',
        title='Practical coding agent workflow guide',
        url='https://example.com/workflow-guide',
        summary='Hands-on implementation with benchmark and repo details.',
        source_name='Example',
        source_type='rss',
        domain='example.com',
        published_at=datetime(2026, 3, 4, 10, 0, tzinfo=timezone.utc),
        priority=6.0,
        section_hint='business',
        metrics={'points': 35.0},
    )
    score_articles([article], feed_dt=datetime(2026, 3, 4, 12, 0, tzinfo=timezone.utc))
    assert 0.0 <= article.source_quality_score <= 10.0
    assert 0.0 <= article.recency_score <= 10.0
    assert 0.0 <= article.novelty_score <= 10.0
    assert 0.0 <= article.confidence_score <= 10.0
