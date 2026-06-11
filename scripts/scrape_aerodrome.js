async (page) => {
  const allPools = [];
  
  while (true) {
    // Extract current page pools
    const pools = await page.evaluate(() => {
      const links = document.querySelectorAll('a[href*="deposit?"]');
      const pools = [];
      links.forEach(link => {
        const href = link.getAttribute('href') || '';
        const params = new URLSearchParams(href.split('?')[1]);
        
        const textContent = link.textContent;
        
        // Extract pair name from the row text
        const pairMatch = textContent.match(/Token Image Token Image\s+([^\n]+)/);
        let pairName = '';
        if (pairMatch) {
          pairName = pairMatch[1].trim().split('Concentrated')[0].trim();
        }
        
        // Extract fee tier from URL params
        const feeTier = params.get('type') || '';
        
        // Extract TVL and Volume from text
        const tvlMatch = textContent.match(/TVL\s+~?\$?([\d,.]+)/);
        const volMatch = textContent.match(/Volume\s+~?\$?([\d,.]+)/);
        
        const tvlDisplay = '$' + (tvlMatch ? tvlMatch[1] : '');
        const volumeDisplay = '$' + (volMatch ? volMatch[1] : '');
        
        const status = textContent.includes('Migrating') ? 'migrating' : 'active';
        
        pools.push({
          pair: pairName,
          feeTier,
          tvl: tvlDisplay,
          volume: volumeDisplay,
          status,
          token0: params.get('token0') || '',
          token1: params.get('token1') || '',
          type: params.get('type') || '',
          factory: params.get('factory') || ''
        });
      });
      return pools;
    });
    
    allPools.push(...pools);
    
    // Check if next page button exists and is enabled
    const hasNext = await page.evaluate(() => {
      const buttons = document.querySelectorAll('button');
      for (const btn of buttons) {
        if (!btn.disabled && btn.closest('[class*="pagination"], [ref*="4139"]')) {
          return true;
        }
      }
      // Find the next arrow button - it's ref=e4150 in snapshot
      const nextBtn = document.querySelector('button[aria-label="Go to next page"], .shiki-code-line-btn');
      if (nextBtn && !nextBtn.disabled) return true;
      
      // Check pagination text
      const pagText = document.body.textContent;
      return pagText.includes('Showing 25 out of') && 
             !pagText.includes(parseInt(pagText.match(/Showing (\d+)/)?.[1] || '0') / 25 >= 
                               parseInt(pagText.match(/out of (\d+)/)?.[1] || '1') / 25);
    });
    
    // Try clicking the next button (the one after disabled prev)
    const clicked = await page.evaluate(() => {
      // Get all buttons in pagination area
      const allBtns = document.querySelectorAll('button');
      for (const btn of allBtns) {
        const rect = btn.getBoundingClientRect();
        // Pagination buttons are at bottom, small size
        if (rect.width < 50 && rect.height < 50 && !btn.disabled && 
            btn.textContent.trim() === '' && rect.top > window.innerHeight - 200) {
          btn.click();
          return true;
        }
      }
      return false;
    });
    
    if (!clicked || !hasNext) break;
    
    await page.waitForTimeout(2000);
  }
  
  // Deduplicate by token0+token1+type
  const seen = new Set();
  const unique = allPools.filter(p => {
    const key = p.token0 + '|' + p.token1 + '|' + p.type;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  
  return JSON.stringify({ total: unique.length, pools: unique });
}