const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 2000, height: 1000 }, deviceScaleFactor: 1 });
  for (const lang of ['ko', 'en']) {
    await p.goto('file://' + __dirname + '/encoder_compare.html?lang=' + lang);
    await p.waitForTimeout(400);
    await p.screenshot({ path: `encoder_compare_${lang}.png`, fullPage: true });
  }
  await b.close();
})();
