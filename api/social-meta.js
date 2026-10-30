const fs = require('fs');
const path = require('path');

const FALLBACK_IMAGE = 'https://res.cloudinary.com/wnlmpwor/image/upload/v1792675323/tin_Viet_Nam.png';
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (ch) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
}[ch]));

module.exports = (req, res) => {
  const id = String(req.query.id || '').slice(0, 300);
  if (!id || id.includes('/') || id.includes('\\')) {
    res.status(400).send('Missing or invalid article id');
    return;
  }
  let records;
  try {
    records = JSON.parse(fs.readFileSync(path.join(process.cwd(), 'social_metadata.json'), 'utf8'));
  } catch (error) {
    res.status(503).send('Social preview metadata is being rebuilt.');
    return;
  }
  const article = records[id];
  if (!article) {
    res.status(404).send('Article not found');
    return;
  }
  const title = esc(article.title || 'AppNho News');
  const description = esc(article.description || article.title || 'Tin tức từ AppNho News');
  const image = esc(article.image || FALLBACK_IMAGE);
  const url = esc(article.url || `https://www.appnho.io.vn/news/article.html?id=${encodeURIComponent(id)}`);
  res.setHeader('Content-Type', 'text/html; charset=utf-8');
  res.setHeader('Cache-Control', 'public, max-age=300, s-maxage=300, stale-while-revalidate=86400');
  res.status(200).send(`<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>${title} | AppNho News</title>
<meta name="description" content="${description}">
<link rel="canonical" href="${url}">
<meta property="og:type" content="article"><meta property="og:site_name" content="AppNho News">
<meta property="og:title" content="${title}"><meta property="og:description" content="${description}">
<meta property="og:url" content="${url}"><meta property="og:image" content="${image}">
<meta property="og:image:secure_url" content="${image}"><meta property="og:image:alt" content="${title}">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="${title}">
<meta name="twitter:description" content="${description}"><meta name="twitter:image" content="${image}">
<meta http-equiv="refresh" content="0;url=${url}"></head><body><p><a href="${url}">${title}</a></p></body></html>`);
};
