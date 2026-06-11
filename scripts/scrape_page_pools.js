async (page) => {
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

      // Extract pair name: "TOKEN / TOKEN"
      const pairMatch = text.match(/([A-Za-z0-9$/.+-]+)\s*\/\s*([A-Za-z0-9$/.+-]+)/);
      if (pairMatch) {
        pool.pair_name = pairMatch[1].trim() + ' / ' + pairMatch[2].trim();
      }

      // Extract TVL: "~$X.XXM" or "~$X,XXX,XXX"
      const tvlMatch = text.match(/TVL\s*~\$(.+?)(?:Fee|Emission|New|$)/s);
      if (tvlMatch) {
        pool.tvl_display = '~$' + tvlMatch[1].trim().split(' ')[0];
      }

      // Extract Volume: "Volume ~$X.XXM"
      const volMatch = text.match(/Volume\s*~\$(.+?)(?:Fees|TVL|New|$)/s);
      if (volMatch) {
        pool.volume_24h_display = '~$' + volMatch[1].trim().split(' ')[0];
      }

      // Extract fee: first percentage that looks like a fee tier
      const feeMatch = text.match(/(\d+\.?\d*)%/);
      if (feeMatch) pool.fee_tier_display = feeMatch[1] + '%';

      if (text.includes('Migrating')) pool.status = 'migrating';

      results.push(pool);
    }
    return results;
  });
  return JSON.stringify(pools);
}