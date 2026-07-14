const fs = require('fs');
const https = require('https');

const [, , sourceUrl, outputPath] = process.argv;

if (!sourceUrl || !outputPath) {
  console.error('Usage: node download-url.js <url> <output>');
  process.exit(2);
}

fs.mkdirSync(require('path').dirname(outputPath), { recursive: true });

function download(url) {
  https.get(url, response => {
    if (response.statusCode >= 300 && response.statusCode < 400 && response.headers.location) {
      download(new URL(response.headers.location, url));
      return;
    }

    if (response.statusCode !== 200) {
      console.error(`Download failed with HTTP ${response.statusCode}`);
      process.exit(1);
    }

    const file = fs.createWriteStream(outputPath);
    response.pipe(file);
    file.on('finish', () => {
      file.close(() => {
        console.log(`Downloaded ${outputPath}`);
      });
    });
  }).on('error', error => {
    console.error(error);
    process.exit(1);
  });
}

download(sourceUrl);
