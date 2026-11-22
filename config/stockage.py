"""Stockage des fichiers statiques : noms hachés (cache-busting), contenu intact.

`ManifestStaticFilesStorage` ajoute l'empreinte du contenu au nom
(`partie.js` → `partie.3f2a….js`) : après un déploiement, le navigateur charge
la nouvelle version au lieu de la copie gardée 7 jours (`expires 7d` de nginx).

`patterns = ()` : aucune réécriture du contenu (url() des CSS, sourceMappingURL
des JS). Réécrire changerait les octets des fichiers vendus et casserait leurs
hashes SRI ; le `.map` absent de Bootstrap ferait aussi échouer collectstatic.
Les CSS du site n'ont pas d'url() à réécrire ; les originaux non hachés restent
copiés à côté, les chemins relatifs (pièces de chessboard.js) fonctionnent donc.
"""

from django.contrib.staticfiles.storage import ManifestStaticFilesStorage


class StatiquesHaches(ManifestStaticFilesStorage):
    patterns = ()
