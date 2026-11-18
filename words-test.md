# Words test

`scripts/words-test` sent the words section of `README.md`, every help text of the `videotape` command, and every error message in the `videotape` package to claude-opus-5-5. It asked for each place that names a concept by another word than the words section gives it, or gives a word of the section another meaning.

## The places

No place does this. Every help text and every error message names each concept of the words section by the section's word, and it uses each of the section's words only in the section's meaning.

## Tokens and cost

- claude-opus-5-5: 28,234 input tokens, 12,176 output tokens, $0.3565
