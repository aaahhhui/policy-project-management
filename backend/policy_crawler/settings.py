BOT_NAME = "policy_crawler"
SPIDER_MODULES = ["policy_crawler.spiders"]
NEWSPIDER_MODULE = "policy_crawler.spiders"
ROBOTSTXT_OBEY = True
CONCURRENT_REQUESTS_PER_DOMAIN = 2
DOWNLOAD_DELAY = 0.8
DOWNLOAD_TIMEOUT = 20
RETRY_TIMES = 2
USER_AGENT = "SupreiumPolicyCollector/0.1 (+internal policy monitoring)"
COOKIES_ENABLED = False
LOG_LEVEL = "INFO"
ITEM_PIPELINES = {
    "policy_crawler.pipelines.DatabaseIngestionPipeline": 300,
}
