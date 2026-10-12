/* Po zabalení (electron-builder afterPack): appku pro Mac podepíše ad-hoc.
 * Bez certifikátu Applu electron-builder podpis vynechá, a protože mění
 * Info.plist, původní podpis Electronu přestane sedět — na Apple Silicon by
 * appka nešla spustit. Stejně to dělá packaging/mac/build.sh. */
const { execFileSync } = require('child_process');
const path = require('path');

exports.default = async function adhocPodpis(context) {
  if (context.electronPlatformName !== 'darwin') return;
  const app = path.join(context.appOutDir, `${context.packager.appInfo.productFilename}.app`);
  execFileSync('codesign', ['--force', '--deep', '--sign', '-', app], { stdio: 'inherit' });
  execFileSync('codesign', ['--verify', '--deep', '--strict', app], { stdio: 'inherit' });
  console.log('  ad-hoc podpis:', app);
};
