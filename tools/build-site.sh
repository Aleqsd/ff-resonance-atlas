#!/usr/bin/env bash
# Builds the project page (docs/) into _site/ with the same Jekyll, theme and plugins as GitHub Pages.
# Cloudflare Workers Builds runs it before `npx wrangler deploy`; locally it needs Ruby and Bundler.
set -euo pipefail
cd "$(dirname "$0")/.."
bundle install
JEKYLL_ENV=production PAGES_REPO_NWO=Aleqsd/ff-resonance-atlas \
  bundle exec jekyll build --source docs --destination _site --config docs/_config.yml
