##########################################################################################
#
# Script name: config.py
#
# Description: Static configuration and section taxonomy for the daily AI feed.
#
##########################################################################################

from dataclasses import dataclass


# ****************************************************************************************
# Global data and configuration
# ****************************************************************************************


@dataclass(frozen=True)
class Section:
    order: int
    slug: str
    label: str
    description: str


SECTIONS = [
    Section(
        order=0,
        slug='big-announcements',
        label='0) Big Announcements',
        description='Major announcements, launches, policy moves, and high-signal market shifts.',
    ),
    Section(
        order=1,
        slug='engineering',
        label='1) Engineering',
        description='How engineers use AI in daily workflows: agents, tooling, benchmarks, and workforce impact.',
    ),
    Section(
        order=2,
        slug='product-development',
        label='2) Product Development',
        description='How PMs and product teams ship faster with AI and redesign team workflows.',
    ),
    Section(
        order=3,
        slug='business',
        label='3) Software Development',
        description='Actionable software development workflows: agents, skills, and how-to implementation patterns.',
    ),
    Section(
        order=4,
        slug='under-the-radar',
        label='4) Under the Radar',
        description='Small blogs, low-key launches, and overlooked ideas that matter.',
    ),
    Section(
        order=5,
        slug='for-fun',
        label='5) For Fun',
        description='Creative, weird, and playful AI experiments worth sharing.',
    ),
]

SECTION_BY_SLUG = {section.slug: section for section in SECTIONS}

KEYWORDS = {
    'big-announcements': [
        'announce',
        'launch',
        'release',
        'introduce',
        'partnership',
        'acquisition',
        'merger',
        'policy',
        'regulation',
        'executive order',
        'funding',
        'raised',
        'series',
        'military',
        'defense',
        'white house',
    ],
    'engineering': [
        'agent',
        'sdk',
        'api',
        'benchmark',
        'eval',
        'framework',
        'open source',
        'repo',
        'repository',
        'copilot',
        'code',
        'devops',
        'prompt engineering',
        'compiler',
        'testing',
        'deployment',
    ],
    'product-development': [
        'product',
        'pm',
        'roadmap',
        'user research',
        'prototype',
        'experimentation',
        'retention',
        'activation',
        'onboarding',
        'feature design',
        'ux',
        'ui',
        'product ops',
    ],
    'business': [
        'agent',
        'coding agent',
        'workflow',
        'playbook',
        'runbook',
        'how to',
        'tutorial',
        'guide',
        'implementation',
        'code generation',
        'debugging',
        'refactor',
        'test',
        'ci',
        'pull request',
        'developer productivity',
        'automation',
        'stack',
        'toolchain',
        'repo',
        'sdk',
        'api',
        'prompt',
    ],
    'under-the-radar': [
        'notes',
        'journal',
        'small model',
        'tiny',
        'niche',
        'case study',
        'field notes',
        'quietly',
        'overlooked',
        'indie',
        'solo',
    ],
    'for-fun': [
        'game',
        'music',
        'art',
        'meme',
        'comic',
        'movie',
        'robot dance',
        'simulation',
        'toy',
        'fun',
        'weird',
        'hackathon',
    ],
}

SECTION_TARGET_MIN = 3
SECTION_TARGET_MAX = 5
RECENCY_REQUIRED_HOURS = 24.0

BUSINESS_PRACTICAL_KEYWORDS = [
    'agent',
    'coding agent',
    'workflow',
    'playbook',
    'runbook',
    'how to',
    'tutorial',
    'guide',
    'implementation',
    'code generation',
    'debugging',
    'refactor',
    'test',
    'ci',
    'pull request',
    'developer productivity',
    'stack',
    'toolchain',
    'repo',
    'sdk',
    'api',
    'prompt',
    'automation',
]

BUSINESS_ANNOUNCEMENT_KEYWORDS = [
    'announce',
    'announcing',
    'launch',
    'launched',
    'release',
    'released',
    'partnership',
    'joint statement',
    'funding',
    'series a',
    'series b',
    'series c',
    'ipo',
    'acquisition',
    'merger',
    'valuation',
    'quarterly results',
    'earnings',
]

MAINSTREAM_DOMAINS = {
    'openai.com',
    'anthropic.com',
    'google.com',
    'deepmind.google',
    'microsoft.com',
    'meta.com',
    'apple.com',
    'amazon.com',
    'aws.amazon.com',
    'techcrunch.com',
    'theverge.com',
    'wired.com',
    'venturebeat.com',
    'bloomberg.com',
    'reuters.com',
    'nytimes.com',
    'wsj.com',
    'ft.com',
}

BIG_ANNOUNCEMENT_DOMAINS = {
    'openai.com',
    'anthropic.com',
    'deepmind.google',
    'ai.google',
    'microsoft.com',
    'meta.com',
    'apple.com',
    'aws.amazon.com',
    'nvidia.com',
    'whitehouse.gov',
    'defense.gov',
}
