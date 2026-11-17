# Visitor Runs play on the public server

The public dashboard at llmbecomehuman.com has no authentication, yet it lets any visitor start a Run with their own API key. The key is posted to the server and used there, and the Run plays on our cluster. We considered showing visitors only the CLI command to run themselves, or allowing dashboard Runs only on local installs. We chose server-side Visitor Runs because the point is to grow the set of models everyone can compare: the first complete Run of a model nobody has run yet becomes public. A Run played on someone else's machine can't do that without an upload path we would have to trust even less.

## Consequences

- The key is held in memory for the life of the Run only. It is never written to the run folder, logs or anything else on disk. A Run cut off by a restart or redeploy cannot be resumed, because its key is gone.
- At most two Visitor Runs play at once across the site, so CPU use and outbound calls stay bounded.
- Visitor Runs live on a persistent volume, separate from the Runs baked into the image. Keel redeploys on every push to `main` and cut off any Visitor Runs in progress; those stay as partial Runs.
- Every Visitor Run is kept, private ones included, and the operator can see them all by pointing a local dashboard at the volume.
- The feature sits behind `dashboard --allow-own-runs`. Turning that flag off removes the form and the endpoints.
