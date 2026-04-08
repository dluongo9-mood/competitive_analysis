"""Test SimilarWeb browser scraping for a few top gummy brands."""
import asyncio
from playwright.async_api import async_playwright

TEST_DOMAINS = [
    "trehouse.com",
    "moonwlkr.com",
    "cbdfx.com",
    "mellowfellow.fun",
    "dadgrass.com",
]

EXTRACT_JS = """
() => {
    const text = document.body.innerText || '';
    const result = {title: document.title, metrics: {}};

    // SimilarWeb shows metrics in engagement section
    // Look for patterns like "Total Visits 1.2M" or "Bounce Rate 45.3%"
    const patterns = [
        ['totalVisits', /Total Visits[\\s\\n]+([\\d.]+[KMB]?)/i],
        ['bounceRate', /Bounce Rate[\\s\\n]+([\\d.]+%)/i],
        ['pagesPerVisit', /Pages per Visit[\\s\\n]+([\\d.]+)/i],
        ['avgDuration', /Avg Visit Duration[\\s\\n]+(\\d+:\\d+)/i],
        ['monthlyVisits', /Monthly Visits[\\s\\n]+([\\d.]+[KMB]?)/i],
        ['globalRank', /Global Rank[\\s\\n]*#?([\\d,]+)/i],
        ['countryRank', /Country Rank[\\s\\n]*#?([\\d,]+)/i],
    ];

    for (const [key, re] of patterns) {
        const m = text.match(re);
        if (m) result.metrics[key] = m[1];
    }

    // Try to get monthly visits from engagement overview area
    // Sometimes shown as "1.2M" near "Total Visits"
    const visitMatch = text.match(/Total Visits[\\s\\S]{0,30}?([\\d.]+[KMB])/i);
    if (visitMatch && !result.metrics.totalVisits) {
        result.metrics.totalVisits = visitMatch[1];
    }

    // Traffic sources
    const srcPatterns = [
        ['direct', /Direct[\\s\\n]+(\\d+\\.?\\d*%)/],
        ['search', /(?:Organic )?Search[\\s\\n]+(\\d+\\.?\\d*%)/],
        ['social', /Social[\\s\\n]+(\\d+\\.?\\d*%)/],
        ['referral', /Referrals?[\\s\\n]+(\\d+\\.?\\d*%)/],
        ['paid', /Paid[\\s\\n]+(\\d+\\.?\\d*%)/],
    ];
    result.trafficSources = {};
    for (const [key, re] of srcPatterns) {
        const m = text.match(re);
        if (m) result.trafficSources[key] = m[1];
    }

    // Monthly trend - look for month labels and values
    // This may be in chart form, harder to extract

    // Get a text snippet for debugging
    result.textSnippet = text.substring(0, 2500);

    return result;
}
"""


async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1440, "height": 900},
        )
        page = await ctx.new_page()

        for domain in TEST_DOMAINS:
            url = f"https://www.similarweb.com/website/{domain}/"
            print(f"\n{'='*60}")
            print(f"  {domain}")
            print(f"{'='*60}")
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(4000)

                info = await page.evaluate(EXTRACT_JS)

                print(f"Title: {info['title'][:60]}")
                print(f"Metrics: {info['metrics']}")
                print(f"Traffic sources: {info['trafficSources']}")

                if not info['metrics']:
                    # Print text snippet for debugging
                    print(f"\nText snippet (first 500):\n{info['textSnippet'][:500]}")

            except Exception as e:
                print(f"Error: {e}")

            await asyncio.sleep(3)

        await browser.close()

asyncio.run(main())
