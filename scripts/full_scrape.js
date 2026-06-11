async (page) => {
  const allPools = [];
  let pageCount = 0;
  const maxPages = 50;

  while (pageCount < maxPages) {
    pageCount++;

    // Scroll to ensure all pools are rendered
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await page.waitForTimeout(1000);
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.waitForTimeout(500);

    const pools = await page.evaluate(() => {
      const links = document.querySelectorAll('a[href*="/deposit?"]');
      const results = [];
      for (const link of links) {
        const href = link.getAttribute('href');
        const params = new URLSearchParams(href.split('?')[1]);
        const text = link.textContent.trim();

        const pool = {
          pair_name: '',
          tvl_display: '',
          volume_24h_display: '',
          fee_tier_display: '',
          status: 'active',
          pool_type: 'Concentrated',
          token0: params.get('token0'),
          token1: params.get('token1'),
          type: params.get('type'),
          factory: params.get('factory')
        };

        const pairMatch = text.match(/([A-Za-z0-9$/.+-]+)\s*\/\s*([A-Za-z0-9$/.+-]+)/);
        if (pairMatch) {
          pool.pair_name = pairMatch[1].trim() + ' / ' + pairMatch[2].trim();
        }

        const tvlMatch = text.match(/TVL\s*~\$(.+?)(?:Fee|Emission|New|$)/s);
        if (tvlMatch) {
          pool.tvl_display = '~$' + tvlMatch[1].trim().split(' ')[0];
        }

        const volMatch = text.match(/Volume\s*~\$(.+?)(?:Fees|TVL|New|$)/s);
        if (volMatch) {
          pool.volume_24h_display = '~$' + volMatch[1].trim().split(' ')[0];
        }

        const feeMatch = text.match(/(\d+\.?\d*)%/);
        if (feeMatch) pool.fee_tier_display = feeMatch[1] + '%';

        if (text.includes('Migrating')) pool.status = 'migrating';

        results.push(pool);
      }
      return results;
    });

    allPools.push(...pools);
    console.log(`Page ${pageCount}: extracted ${pools.length} pools. Running total: ${allPools.length}`);

    if (pools.length === 0) break;

    // Find Next button - try multiple selectors
    const nextBtn = await page.$('button[aria-label="Go to next page"], nav button:last-child, [class*="Pagination"] button:not([disabled]):last-child');
    if (!nextBtn) {
      console.log(`No next button found on page ${pageCount}. Stopping.`);
      break;
    }

    const isDisabled = await nextBtn.evaluate(el => el.disabled || el.getAttribute('aria-disabled') === 'true' || el.textContent.trim() === '');
    if (isDisabled) {
      console.log(`Next button disabled on page ${pageCount}. Done.`);
      break;
    }

    await nextBtn.click();
    await page.waitForTimeout(3000);
  }

  return JSON.stringify({ count: allPools.length, pageCount, pools: allPools });
}