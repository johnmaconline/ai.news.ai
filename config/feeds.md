# Feed Registry

This file is always checked in addition to `config/sources.yaml`.

Format:
- Use markdown list items (`- ...`) under each section.
- Optional metadata can be added with `| key=value`.
- Example: `- https://example.com/feed.xml | name=Example | section=under-the-radar | tags=ai,engineering`
- LinkedIN users can be URN or profile URL. Optional: `| author_urn=urn:li:person:...`

## 1. URLs

- https://johnmaconline.com/feed | name=johnmaconline.com | section=under-the-radar | tags=under-the-radar,engineering
- https://www.oneusefulthing.org/feed | platform=substack | name=One Useful Thing | section=product-development | tags=product-development,under-the-radar
- https://www.latent.space/feed | platform=substack | name=Latent Space | section=engineering | tags=engineering,under-the-radar
- https://www.interconnects.ai/feed | platform=substack | name=Interconnects AI | section=under-the-radar | tags=under-the-radar,engineering
- https://www.importai.net/feed | platform=substack | name=Import AI | section=engineering | tags=engineering,under-the-radar
- https://www.understandingai.org/feed | platform=substack | name=Understanding AI | section=under-the-radar | tags=under-the-radar,engineering
- https://www.aisnakeoil.com/feed | name=AI Snake Oil | section=under-the-radar | tags=under-the-radar,engineering
- https://newsletter.victordibia.com/feed | platform=substack | name=Designing with AI | section=product-development | tags=product-development,under-the-radar
- https://newsletter.semianalysis.com/feed | platform=substack | name=SemiAnalysis | section=engineering | tags=engineering,business
- https://www.exponentialview.co/feed | platform=substack | name=Exponential View | section=engineering | tags=engineering,business
- https://www.notboring.co/feed | platform=substack | name=Not Boring | section=product-development | tags=product-development,business
- https://lastweekin.ai/feed/ | name=Last Week in AI | section=engineering | tags=engineering,under-the-radar
- https://www.aitidbits.ai/feed | platform=substack | name=AI Tidbits | section=under-the-radar | tags=under-the-radar,for-fun
- https://www.ben-evans.com/benedictevans?format=rss | name=Benedict Evans | section=engineering | tags=engineering,business
- https://stratechery.com/feed/ | name=Stratechery | section=engineering | tags=engineering,business
- https://www.aiweekly.co/issues.rss | name=AI Weekly | section=engineering | tags=engineering,curators
- https://www.tldrnewsletter.com/rss | name=TLDR (AI Edition) | section=engineering | tags=engineering,curators
- https://www.thealgorithmicbridge.com/feed | name=The Algorithmic Bridge | section=business | tags=business,curators,engineering
- https://news.smol.ai/rss.xml | name=smol.ai news | section=engineering | tags=engineering,curators,under-the-radar
- https://newsletter.pragmaticengineer.com/feed | name=Pragmatic Engineer | section=business | tags=business,engineering,curators
- https://every.to/chain-of-thought/feed | name=Every: Chain of Thought | section=product-development | tags=product-development,curators

- https://simonwillison.net/atom/everything/ | name=Simon Willison | section=engineering | tags=engineering,under-the-radar
- https://steipete.me/rss.xml | name=Peter Steinberger | section=engineering | tags=engineering,under-the-radar
- https://medium.com/feed/@thdxr | platform=medium | name=Dax Raad (thdxr) | section=engineering | tags=engineering,under-the-radar
- https://swyx.io/feed | name=swyx | section=business | tags=business,engineering,under-the-radar
- https://blog.langchain.dev/rss/ | name=LangChain Blog | section=engineering | tags=engineering,business
- https://sourcegraph.com/blog/rss.xml | name=Sourcegraph Blog | section=business | tags=business,engineering
- https://www.promptfoo.dev/blog/rss.xml | name=Promptfoo Blog | section=practical-prompts | tags=practical-prompts,engineering
- https://blog.cloudflare.com/tag/ai/rss/ | name=Cloudflare AI | section=engineering | tags=engineering
- https://blog.cloudflare.com/tag/workers-ai/rss/ | name=Cloudflare Workers AI | section=business | tags=business,engineering
- https://github.blog/ai-and-ml/feed/ | name=GitHub Blog AI/ML | section=business | tags=business,engineering
- https://huggingface.co/blog/feed.xml | name=Hugging Face Blog | section=engineering | tags=engineering
- https://aws.amazon.com/blogs/machine-learning/feed/ | name=AWS Machine Learning Blog | section=engineering | tags=engineering
- https://www.databricks.com/feed | name=Databricks Blog | section=business | tags=business,engineering
- https://weaviate.io/blog/rss.xml | name=Weaviate Blog | section=engineering | tags=engineering,business
- https://airbyte.com/blog/rss.xml | name=Airbyte Blog | section=engineering | tags=engineering,business
- https://blog.bytebytego.com/feed | name=ByteByteGo | section=business | tags=business,engineering
- https://dev.to/feed/tag/llm | name=DEV.to LLM Tag | section=business | tags=business,engineering,under-the-radar
- https://dev.to/feed/tag/agents | name=DEV.to Agents Tag | section=business | tags=business,engineering,under-the-radar
- https://dev.to/feed/tag/ai | name=DEV.to AI Tag | section=engineering | tags=engineering,under-the-radar
- https://www.infoq.com/feed/ai-ml-data-eng | name=InfoQ AI/ML/Data Engineering | section=business | tags=business,engineering
- https://martinfowler.com/feed.atom | name=Martin Fowler | section=business | tags=business,engineering
- https://www.fast.ai/index.xml | name=fast.ai | section=engineering | tags=engineering,under-the-radar
- https://www.jasonwei.net/blog/rss.xml | name=Jason Wei Blog | section=engineering | tags=engineering,under-the-radar
- https://lilianweng.github.io/posts/index.xml | name=Lilian Weng (Lil'Log) | section=engineering | tags=engineering,under-the-radar
- https://huyenchip.com/feed.xml | name=Chip Huyen | section=engineering | tags=engineering,product-development

- https://www.lennysnewsletter.com/feed | platform=substack | name=Lenny's Newsletter | section=product-development | tags=product-development,business
- https://www.producttalk.org/feed/ | name=Product Talk | section=product-development | tags=product-development,business
- https://www.productcoalition.com/feed | name=Product Coalition | section=product-development | tags=product-development,business
- https://www.ycombinator.com/blog/feed | name=Y Combinator Blog | section=product-development | tags=product-development,business
- https://www.producthunt.com/feed | name=Product Hunt | section=for-fun | tags=for-fun,product-development

- https://openai.com/news/rss.xml | name=OpenAI News | section=engineering | tags=engineering
- https://blog.google/technology/ai/rss/ | name=Google AI Blog | section=engineering | tags=engineering
- https://research.google/blog/rss/ | name=Google Research Blog | section=engineering | tags=engineering
- https://blog.google/technology/developers/rss/ | name=Google Developer Blog | section=engineering | tags=engineering
- https://www.microsoft.com/en-us/ai/blog/feed/ | name=Microsoft AI Blog | section=engineering | tags=engineering,product-development
- https://www.microsoft.com/en-us/research/blog/feed/ | name=Microsoft Research Blog | section=engineering | tags=engineering
- https://research.facebook.com/feed/ | name=Meta Research | section=engineering | tags=engineering
- https://techcrunch.com/category/artificial-intelligence/feed/ | name=TechCrunch AI | section=engineering | tags=engineering,business
- https://www.theverge.com/rss/ai-artificial-intelligence/index.xml | name=The Verge AI | section=engineering | tags=engineering,for-fun
- https://www.technologyreview.com/topic/artificial-intelligence/feed/ | name=MIT Technology Review AI | section=engineering | tags=engineering,business
- https://www.wired.com/feed/tag/ai/latest/rss | name=Wired AI | section=engineering | tags=engineering,for-fun
- https://www.theguardian.com/technology/artificialintelligenceai/rss | name=The Guardian AI | section=engineering | tags=engineering,business
- https://www.marktechpost.com/feed/ | name=MarkTechPost | section=under-the-radar | tags=under-the-radar,engineering

- http://export.arxiv.org/api/query?search_query=cat:cs.AI+OR+cat:cs.LG&sortBy=submittedDate&sortOrder=descending&start=0&max_results=40 | name=arXiv cs.AI+cs.LG | section=engineering | tags=engineering,under-the-radar,research
- http://export.arxiv.org/api/query?search_query=all:agentic+ai&sortBy=submittedDate&sortOrder=descending&start=0&max_results=40 | name=arXiv Agentic AI Query | section=business | tags=business,engineering,research
- https://bair.berkeley.edu/blog/feed.xml | name=Berkeley AI Research Blog | section=under-the-radar | tags=under-the-radar,research,engineering
- https://www.lesswrong.com/feed.xml | name=LessWrong | section=under-the-radar | tags=under-the-radar,research
- https://alignmentforum.org/feed.xml | name=AI Alignment Forum | section=under-the-radar | tags=under-the-radar,research
- https://www.reddit.com/r/LocalLLaMA/.rss | name=Reddit r/LocalLLaMA | section=under-the-radar | tags=under-the-radar,engineering
- https://www.reddit.com/r/MachineLearning/.rss | name=Reddit r/MachineLearning | section=under-the-radar | tags=under-the-radar,research
- https://www.reddit.com/r/artificial/.rss | name=Reddit r/artificial | section=under-the-radar | tags=under-the-radar,for-fun
- https://www.reddit.com/r/ChatGPTCoding/.rss | name=Reddit r/ChatGPTCoding | section=business | tags=business,engineering,under-the-radar

- https://blog.langchain.com/rss/ | name=LangChain Blog | section=engineering | tags=autodiscovered,engineering,under-the-radar | discovered=auto
- https://www.normaltech.ai/feed | name=AI as Normal Technology | section=under-the-radar | tags=autodiscovered,under-the-radar | discovered=auto
- https://jack-clark.net/feed/ | name=Import AI | section=engineering | tags=autodiscovered,engineering,under-the-radar | discovered=auto
- https://news.microsoft.com/source/feed/ | name=Source | section=engineering | tags=autodiscovered,engineering,under-the-radar | discovered=auto
- https://newsletter.danielpaleka.com/feed | name=Daniel Paleka's Newsletter | section=engineering | tags=autodiscovered,engineering,under-the-radar | discovered=auto
- https://tonsky.me/atom.xml | name=tonsky.me | section=engineering | tags=autodiscovered,engineering,under-the-radar | discovered=auto
- https://codingfox.net.pl/index.xml | name=CodingFox | section=engineering | tags=autodiscovered,engineering,under-the-radar | discovered=auto
- https://futurism.com/feed | name=Futurism | section=engineering | tags=autodiscovered,engineering,under-the-radar | discovered=auto
- https://www.svd.se/feed/articles.rss | name=SvD - Artiklar | section=engineering | tags=autodiscovered,engineering,under-the-radar | discovered=auto
- https://gizmodo.com/feed | name=Gizmodo | section=engineering | tags=autodiscovered,engineering,under-the-radar | discovered=auto

- https://www.seangoedecke.com/rss.xml | name=seangoedecke.com RSS feed | section=engineering | tags=autodiscovered,engineering,under-the-radar | discovered=auto
- https://arstechnica.com/feed | name=Ars Technica | section=engineering | tags=autodiscovered,engineering,under-the-radar | discovered=auto
- https://www.ifixit.com/News/rss | name=iFixit News | section=engineering | tags=autodiscovered,engineering,under-the-radar | discovered=auto
- https://blog.matthewbrunelle.com/rss/ | name=Matthew Brunelle's Blog | section=engineering | tags=autodiscovered,engineering,under-the-radar | discovered=auto
- https://www.windowslatest.com/feed/ | name=Windows Latest | section=engineering | tags=autodiscovered,engineering,under-the-radar | discovered=auto
- http://karpathy.github.io/feed.xml | name=Andrej Karpathy blog | section=engineering | tags=autodiscovered,engineering,under-the-radar | discovered=auto
- https://matklad.github.io/feed.xml | name=matklad | section=engineering | tags=autodiscovered,engineering,under-the-radar | discovered=auto
- https://copyrightlately.com/feed | name=Copyright Lately | section=engineering | tags=autodiscovered,engineering,under-the-radar | discovered=auto
- https://www.tyleo.com/rss.xml | name=tyleo.com | section=engineering | tags=autodiscovered,engineering,under-the-radar | discovered=auto
- https://engineering.fb.com/feed/ | name=Engineering at Meta | section=engineering | tags=autodiscovered,engineering,under-the-radar | discovered=auto

- https://www.theregister.com/headlines.atom | name=The Register | section=engineering | tags=autodiscovered,engineering,under-the-radar | discovered=auto
- https://blogs.windows.com/feed | name=Windows Blog | section=engineering | tags=autodiscovered,engineering,under-the-radar | discovered=auto
- https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml | name=NYT > Top Stories | section=engineering | tags=autodiscovered,engineering,under-the-radar | discovered=auto
- https://www.aol.com/rss-index.xml | name=AOL.com | section=engineering | tags=autodiscovered,engineering,under-the-radar | discovered=auto
- https://www.hcamag.com/rss | name=Human Resources Director Australia | section=engineering | tags=autodiscovered,engineering,under-the-radar | discovered=auto
- https://www.latimes.com/index.rss | name=News from California, across the nation and world - Los Angeles Times | section=engineering | tags=autodiscovered,engineering,under-the-radar | discovered=auto
- https://markets.businessinsider.com/rss | name=All Content from Business Insider | section=engineering | tags=autodiscovered,engineering,under-the-radar | discovered=auto
- https://en.antaranews.com/feed | name=ANTARA News - Latest Indonesia News | section=engineering | tags=autodiscovered,engineering,under-the-radar | discovered=auto
- https://feeds.businessinsider.com/custom/all | name=All Content from Business Insider | section=engineering | tags=autodiscovered,engineering,under-the-radar | discovered=auto
- https://www.storagereview.com/feed | name=StorageReview.com | section=engineering | tags=autodiscovered,engineering,under-the-radar | discovered=auto
- https://www.tradingview.com/feed | name=TradingView Ideas | section=engineering | tags=autodiscovered,engineering,under-the-radar | discovered=auto

- https://futurecio.tech/feed/ | name=FutureCIO | section=engineering | tags=autodiscovered,engineering,under-the-radar | discovered=auto
- https://www.thehansindia.com/google_feeds.xml | name=Andhra Pradesh Breaking News, Telangana News, Hyderabad News Updates, National News, Breaking News | section=engineering | tags=autodiscovered,engineering,under-the-radar | discovered=auto
- https://www.stocktitan.net/rss | name=Latest News - Stock Titan | section=engineering | tags=autodiscovered,engineering,under-the-radar | discovered=auto
- https://rollcall.com/feed | name=Roll Call | section=engineering | tags=autodiscovered,engineering,under-the-radar | discovered=auto
- https://accesspartnership.com/feed/ | name=Access Partnership | section=engineering | tags=autodiscovered,engineering,under-the-radar | discovered=auto
- https://www.mckinsey.com/rss | name=McKinsey Insights & Publications | section=engineering | tags=autodiscovered,engineering,under-the-radar | discovered=auto
- https://www.sitepoint.com/feed | name=SitePoint | section=engineering | tags=autodiscovered,engineering,under-the-radar | discovered=auto
- https://siliconangle.com/feed/ | name=SiliconANGLE | section=engineering | tags=autodiscovered,engineering,under-the-radar | discovered=auto

- https://tldr.tech/rss | name=TLDR RSS Feed | section=engineering | tags=autodiscovered,engineering,under-the-radar | discovered=auto
## 2. LinkedIN users

- https://www.linkedin.com/in/emollick/ | name=Ethan Mollick | section=product-development | tags=product-development,under-the-radar,social
- https://www.linkedin.com/in/andrewng/ | name=Andrew Ng | section=engineering | tags=engineering,education,social
- https://www.linkedin.com/in/karpathy/ | name=Andrej Karpathy | section=engineering | tags=engineering,under-the-radar,social
- https://www.linkedin.com/in/satyanadella/ | name=Satya Nadella | section=engineering | tags=engineering,business,social
- https://www.linkedin.com/company/openai/ | name=OpenAI (LinkedIn) | section=engineering | tags=engineering,social
- https://www.linkedin.com/company/anthropicresearch/ | name=Anthropic (LinkedIn) | section=engineering | tags=engineering,social
- https://www.linkedin.com/company/google-deepmind/ | name=Google DeepMind (LinkedIn) | section=engineering | tags=engineering,social
- https://www.linkedin.com/company/huggingface/ | name=Hugging Face (LinkedIn) | section=engineering | tags=engineering,social
- https://www.linkedin.com/company/microsoft/ | name=Microsoft (LinkedIn) | section=engineering | tags=engineering,social
- https://www.linkedin.com/company/nvidia/ | name=NVIDIA (LinkedIn) | section=engineering | tags=engineering,social
- https://www.linkedin.com/company/meta/ | name=Meta (LinkedIn) | section=engineering | tags=engineering,social
- https://www.linkedin.com/company/databricks/ | name=Databricks (LinkedIn) | section=business | tags=business,social
- https://www.linkedin.com/company/sourcegraph/ | name=Sourcegraph (LinkedIn) | section=business | tags=business,social
- https://www.linkedin.com/company/langchain/ | name=LangChain (LinkedIn) | section=business | tags=business,engineering,social
- https://www.linkedin.com/company/perplexity-ai/ | name=Perplexity (LinkedIn) | section=product-development | tags=product-development,social

## 3. X users

- @swyx | name=swyx | section=business | tags=business,engineering,social
- @karpathy | name=Andrej Karpathy | section=engineering | tags=engineering,under-the-radar,social
- @AndrewYNg | name=Andrew Ng | section=engineering | tags=engineering,social
- @emollick | name=Ethan Mollick | section=product-development | tags=product-development,social
- @sama | name=Sam Altman | section=engineering | tags=engineering,social
- @fchollet | name=Francois Chollet | section=engineering | tags=engineering,social
- @jeremyphoward | name=Jeremy Howard | section=engineering | tags=engineering,under-the-radar,social
- @ylecun | name=Yann LeCun | section=engineering | tags=engineering,research,social
- @lilianweng | name=Lilian Weng | section=engineering | tags=engineering,research,social
- @vboykis | name=Vicki Boykis | section=under-the-radar | tags=under-the-radar,engineering,social
- @OpenAI | name=OpenAI | section=engineering | tags=engineering,social
- @AnthropicAI | name=Anthropic | section=engineering | tags=engineering,social
- @GoogleDeepMind | name=Google DeepMind | section=engineering | tags=engineering,social
- @huggingface | name=Hugging Face | section=engineering | tags=engineering,social
- @LangChainAI | name=LangChain | section=business | tags=business,engineering,social
- @LlamaIndex | name=LlamaIndex | section=business | tags=business,engineering,social
- @sourcegraph | name=Sourcegraph | section=business | tags=business,engineering,social
- @perplexity_ai | name=Perplexity | section=product-development | tags=product-development,social
- @v0 | name=Vercel v0 | section=for-fun | tags=for-fun,product-development,social
- @levelsio | name=levelsio | section=business | tags=business,under-the-radar,social

## 4. other

- Add candidate feeds here before promotion to sections.
- For LinkedIn URLs, add `author_urn` metadata once available to enable API ingestion.
