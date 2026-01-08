# Release process

This section documents the steps to make a release of docstub.
Depending on the release type not all steps may be mandatory – use appropriate judgement.


## Create release notes

Generate a [read-only GitHub token](https://github.com/settings/personal-access-tokens), install [changelist](https://github.com/scientific-python/changelist), and generate a first draft of the release notes with it.

```shell
pip install changelist

RELEASE_TAG=...
PREV_TAG=...
export GH_TOKEN=...

changelist scientific-python/docstub \
    --version "${RELEASE_TAG}" \
    --out "doc/release_notes/v${RELEASE_TAG}.md" \
    "${PREV_TAG}" main
```

- `RELEASE_TAG` is the tag of the current release (for example `v1.1.0`)
- `PREV_TAG` is the tag of the previous release (for example `v1.0.0`).

So changelist will generate notes based on the changes between `${PREV_TAG}..main`.

Review and update `doc/release_notes/v${RELEASE_TAG}.md`.
Don't forget to add the new document to `doc/release_notes/index.md`.

Create a pull request with the new release notes.
If desired, include this pull request in the release notes, too.


## Create a new tag

Once the pull request with the release notes is merged, tag the resulting commit with the desired version tag.
This should be a signed tag.

```shell
git tag --sign "v${RELEASE_TAG}"
```

Include the release notes in the tag's message in the same formatting style as other release tags.

Review and then push the tag:

```shell
git push origin "v${RELEASE_TAG}"
```


## Create a new "version" on Read the Docs

Login to https://app.readthedocs.org/projects/docstub.

Create a [new version](https://app.readthedocs.org/dashboard/docstub/version/create/) for the tag corresponding to the new release.


## Trigger release workflow on GitHub

Trigger [docstub's release workflow on GitHub](https://github.com/scientific-python/docstub/actions/workflows/cd.yml).
As a security measure, this workflow needs to be approved by one eligible maintainer.
If successful, the workflow will build the package and push it to PyPI.


## Format and publish GitHub release

[Create a new release draft](https://github.com/scientific-python/docstub/releases/new) and copy the content of `doc/release_notes/v${RELEASE_TAG}.md` into it.
(Remove the duplicate level 1 headline in the first line.)

Review and publish.
