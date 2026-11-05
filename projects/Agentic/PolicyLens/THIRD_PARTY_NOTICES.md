# Third-party notices

## GitLab public handbook corpus

The six Markdown snapshots under `data/corpus/` are adapted from the public GitLab handbook: main article text was extracted, navigation and markup were removed, and headings were retained. Original authors: GitLab and handbook contributors. Canonical URLs and fetch timestamps are recorded per document in `data/corpus/sources.json`.

The handbook source repository's license was retrieved from:
https://gitlab.com/gitlab-com/content-sites/handbook/-/raw/main/LICENSE

```text
Copyright (c) 2011-present GitLab B.V.

With regard to the GitLab Software:

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.

For all third party components incorporated into the GitLab Software, those
components are licensed under the original license provided by the owner of the
applicable component.
```

This project is not affiliated with, endorsed by, or an official product of GitLab.

## Tokenizer vocabulary

`data/tokenizer/` contains the cl100k_base vocabulary distributed by OpenAI's tiktoken project. It is bundled to avoid a download during offline chunking. Source: https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken. The tiktoken package is MIT licensed; its installed distribution includes its license. The cache key and file hash are checked by tiktoken's loader.

## Python dependencies

Third-party Python packages retain their respective licenses in their installed distributions. `uv.lock` and `requirements.txt` record the versions used.

