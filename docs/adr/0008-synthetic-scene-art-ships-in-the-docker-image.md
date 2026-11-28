# Synthetic Scene Art ships in the Docker image

The dashboard used to show the game's own concept art behind the Story and the Flowchart, but only on a local install: the art was copyrighted, so `images/` was gitignored and the Docker image never included it, and the public site had none. We replaced it with Synthetic Scene Art, made by an image model from our own prompts, and chose to show it on the public site too. We considered a separate persistent volume filled by hand, and object storage behind a CDN. We chose to commit the WebP files to git and bake them into the Docker image, because then the images are versioned together with `data/scene-art.json`, so the manifest can never name a scene whose image is missing, and CI already builds and deploys the image.

## Consequences

- The images are in git history and on a public site. Taking them back means rewriting history and purging caches, not just deleting files. They depict the game's characters, so they are fan art of someone else's property.
- One size for everyone: scenes at 1280 px, WebP quality 65 (about 40 KB each, about 7 MB in all). The art is always shown blurred and desaturated, so a larger file or a separate phone size would add bytes nobody sees. The title art keeps its native width because it is shown sharp.
- Caching and preloading were deliberately left as they were: one-day browser caching, no Cloudflare edge caching (the URLs have no file extension), and each image fetched only when its scene is reached. Change them only when slow art is actually observed, not in advance.
- There is no "bring your own art" path any more. Anyone who wants different art replaces the files in `images/`; the dashboard does not care where they came from.
- Raw generated PNGs never go into git or the image, only the converted WebP files named in the manifest.
