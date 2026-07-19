# Summary

Produce a high-level, grounded summary of a document or section — without inventing
anything not in the source.

## When to use
The user asks to "summarize", "give the key findings", or "what does this report say
about X".

## Steps
1. Gather the source material — do NOT summarize from memory:
   - For a whole-document / section summary, use `read_page` on the relevant pages
     (the "Data Highlights" pages near the front are the richest; the Contents page
     lists section page numbers).
   - For a topic summary, use `search_documents` to pull the relevant lines first.
2. Write 4–8 concise bullet points capturing the main figures and findings.
3. Attach a citation (document + page) to every bullet that states a fact. If a claim
   isn't supported by what you read, drop it.
4. Keep numbers exactly as written in the source (do not round or reformat).

## Output shape
```
**<Document / topic> — key findings**
- <finding with a concrete figure>  [Doc, p.N]
- <finding>  [Doc, p.N]
...
```

## Refuse gracefully
If the requested section/topic isn't present in the documents, say so plainly rather
than guessing. Do not fill gaps with outside knowledge.
