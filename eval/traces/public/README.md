# Public traces

`ds-row*.json` are 8 rows of [blythet/deepseek-v4-flash-swe-cot](https://huggingface.co/datasets/blythet/deepseek-v4-flash-swe-cot)
(file `sft_all.jsonl`, revision `2ab7bee2037340d8e7930f19b4a89d8a79add203`, sha256
`4b2f0ce5b1851890f68afc73cf694269be2f9949854700be05caa67087f580e7`). The dataset is released under the
MIT license by its author (Hugging Face user `blythet`); its task instances come from SWE-smith (MIT).
Model: DeepSeek-V4-Flash, with raw `reasoning_content`.

Changes made here: each row was converted to OpenAI chat format (`{"model", "source", "instance_id", "messages"}`).
The dataset stores `tool_calls` as a Python-repr string; it was parsed with `ast.literal_eval` into
OpenAI `tool_calls` objects. Message text and reasoning are unchanged. Rows were picked because they contain
commitment-like phrases (for example "No network." as an environment observation, or "my changes only touch
X and Y") or no commitments at all; all 8 are labelled consistent.

## License of these files (MIT, from the source dataset)

Copyright (c) the dataset author (Hugging Face user `blythet`)

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
documentation files (the "Software"), to deal in the Software without restriction, including without limitation
the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to
permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of
the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE
WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
