import { describe, expect, it } from "vitest";
import { languageName, transcriptLabel } from "./format";

describe("transcriptLabel", () => {
  it("names the languages of a local transcription", () => {
    expect(transcriptLabel("Transcribed on this computer", ["hi", "en"])).toBe(
      "Transcribed on this computer · Hindi, English",
    );
  });
  it("leaves YouTube's own description alone", () => {
    expect(transcriptLabel("YouTube captions · Hindi (auto-generated)", ["hi"])).toBe(
      "YouTube captions · Hindi (auto-generated)",
    );
  });
  it("copes with codes it doesn't know", () => {
    expect(languageName("zz-not-a-language")).toBe("zz-not-a-language");
  });
});
