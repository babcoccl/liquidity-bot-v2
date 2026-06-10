// Aerodrome pool row extractor — v2 with fixed pair_name parsing
// Text format: "WETH / msETH\n0.05%\nConcentrated 50\nMIGRATING\nVolume\n~$48.44M\n...\nTVL\n~$20.61M\n..."

Array.from(document.querySelectorAll('a[href*="/deposit?"]')).map(link => {
  const href = link.getAttribute('href') || '';
  const params = new URLSearchParams((href.split('?')[1]) || '');
  const text = link.innerText || '';

  // Pair: first line before newline
  let pair = (text.split('\n')[0] || '').trim();

  // Fee from URL type param
  const feeType = params.get('type') || '0';

  // Status
  const status = text.includes('Migrating') ? 'migrating' : 'active';

  // TVL: after 'TVL' then '~$X'
  let tvl = '$0';
  const tvlMatch = text.match(/TVL\s+~\$([0-9,]+(?:\.[0-9]+)?)/);
  if (tvlMatch) tvl = '$' + tvlMatch[1];

  // Volume: after 'Volume' then '~$X'
  let vol = '$0';
  const volMatch = text.match(/Volume\s+~\$([0-9,]+(?:\.[0-9]+)?)/);
  if (volMatch) vol = '$' + volMatch[1];

  return {
    pair_name: pair,
    tvl_display: tvl,
    volume_24h_display: vol,
    fee_tier_raw: feeType,
    status: status,
    token0: params.get('token0') || '',
    token1: params.get('token1') || '',
    factory: params.get('factory') || ''
  };
})