/* Ikony pro electron-builder: vezme je z assets/ v repu (stejné jako okno hubu). */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
const here = path.dirname(fileURLToPath(import.meta.url));
const assets = path.join(here, '..', '..', 'assets');
const out = path.join(here, '..', 'build');
fs.mkdirSync(out, { recursive: true });
fs.copyFileSync(path.join(assets, 'claude-code.png'), path.join(out, 'icon.png'));
fs.copyFileSync(path.join(assets, 'claude-code.ico'), path.join(out, 'icon.ico'));
console.log('ikony zkopírovány do', out);
