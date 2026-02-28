# Feed Registry

This file is always checked in addition to `config/sources.yaml`.

Format:
- Use markdown list items (`- ...`) under each section.
- Optional metadata can be added with `| key=value`.
- Example: `- https://example.com/feed.xml | name=Example | section=under-the-radar | tags=ai,engineering`
- LinkedIN users can be URN or profile URL. Optional: `| author_urn=urn:li:person:...`

## 1. URLs

- https://www.interconnects.ai/feed | name=Interconnects | section=under-the-radar | tags=under-the-radar,engineering
- https://www.latent.space/feed | name=Latent Space | section=under-the-radar | tags=under-the-radar,business
- https://simonwillison.net/atom/everything/ | name=Simon Willison | section=under-the-radar | tags=under-the-radar,engineering

## 2. LinkedIN users

- urn:li:organization:000000 | name=LinkedIn Org Placeholder | section=product-development | tags=product-development,business,social
- https://www.linkedin.com/in/emollick/

## 3. X users

- @swyx | section=under-the-radar | tags=under-the-radar,social
- @karpathy | section=engineering | tags=engineering,social

## 4. other

- Add notes, candidate sources, and ideas here.
