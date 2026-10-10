import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { renderBlocks, renderRich } from "../lib/richText";

function renderText(text: string) {
  return render(<div data-testid="rt-root">{renderBlocks(text)}</div>);
}

describe("renderBlocks — fenced code blocks", () => {
  it("renders a fenced code block as a <pre> with preserved newlines and no ``` markers", () => {
    const text = ["Here is an example:", "```js", "const x = 1;", "const y = 2;", "```"].join(
      "\n",
    );
    const { container } = renderText(text);

    const pre = container.querySelector("pre.rt__pre");
    expect(pre).not.toBeNull();
    expect(container.querySelectorAll("pre")).toHaveLength(1);
    expect(container.querySelector(".rt__code-block pre")).toBe(pre);
    expect(pre?.querySelector("code.rt__pre-code")?.textContent).toBe(
      "const x = 1;\nconst y = 2;",
    );
    expect(container.textContent).not.toContain("```");
  });

  it("keeps code lines raw — markdown inside a fence is not inline-rendered", () => {
    const text = ["```md", "**not bold** and *not italic*", "- not a bullet", "```"].join("\n");
    const { container } = renderText(text);

    const code = container.querySelector("code.rt__pre-code");
    expect(code?.textContent).toBe("**not bold** and *not italic*\n- not a bullet");
    expect(container.querySelector("strong.rt__b")).toBeNull();
    expect(container.querySelector("em.rt__i")).toBeNull();
    expect(container.querySelectorAll("li")).toHaveLength(0);
  });

  it("renders the language label when a language is given", () => {
    const text = ["```ts", "const a: number = 1;", "```"].join("\n");
    const { container } = renderText(text);

    const lang = container.querySelector(".rt__code-lang");
    expect(lang).not.toBeNull();
    expect(lang?.textContent).toBe("ts");
    expect(screen.getByText("ts")).toBeInTheDocument();
  });

  it("omits the language label when no language is given", () => {
    const text = ["```", "plain code", "```"].join("\n");
    const { container } = renderText(text);

    expect(container.querySelector(".rt__code-lang")).toBeNull();
    expect(container.querySelector("code.rt__pre-code")?.textContent).toBe("plain code");
  });

  it("closes the block on a fence of the same character (```go ... ```)", () => {
    const text = [
      "```go",
      'fmt.Println("hi")',
      "```",
      "Back to prose.",
    ].join("\n");
    const { container } = renderText(text);

    expect(container.querySelector("code.rt__pre-code")?.textContent).toBe(
      'fmt.Println("hi")',
    );
    // The closing fence ended the block — trailing text is a paragraph.
    expect(screen.getByText("Back to prose.")).toBeInTheDocument();
  });

  it("supports ~~~ fences", () => {
    const text = ["~~~python", 'print("hello")', "~~~"].join("\n");
    const { container } = renderText(text);

    expect(container.querySelector(".rt__code-lang")?.textContent).toBe("python");
    expect(container.querySelector("code.rt__pre-code")?.textContent).toBe('print("hello")');
  });

  it("renders code from an unterminated fence (mid-stream reveal)", () => {
    const text = ["```sh", "npm install", "npm run build"].join("\n");
    const { container } = renderText(text);

    expect(container.querySelector("code.rt__pre-code")?.textContent).toBe(
      "npm install\nnpm run build",
    );
    expect(container.textContent).not.toContain("```");
  });
});

describe("renderBlocks — inline formatting and blocks (regression guard)", () => {
  it("still renders inline code, bold/italic and links", () => {
    const text = "Use `npm test` and **bold** with *emphasis*. See [FBR](https://www.fbr.gov.pk).";
    const { container } = renderText(text);

    expect(screen.getByText("npm test")).toBeInTheDocument();
    expect(screen.getByText("bold")).toBeInTheDocument();
    expect(screen.getByText("emphasis")).toBeInTheDocument();
    const link = screen.getByRole("link", { name: "FBR" });
    expect(link).toHaveAttribute("href", "https://www.fbr.gov.pk");
    const code = container.querySelector("code.rt__code");
    expect(code).not.toBeNull();
  });

  it("still renders paragraphs and unordered bullets", () => {
    const text = ["First paragraph line.", "", "- alpha", "- beta"].join("\n");
    const { container } = renderText(text);

    expect(screen.getByText("First paragraph line.")).toBeInTheDocument();
    const items = container.querySelectorAll("ul.rt__list li, ul li");
    expect(items).toHaveLength(2);
    expect(items[0].textContent).toBe("alpha");
    expect(items[1].textContent).toBe("beta");
  });

  it("still renders numbered bullets as an ordered list", () => {
    const text = ["1. one", "2. two"].join("\n");
    const { container } = renderText(text);

    const items = container.querySelectorAll("ol li");
    expect(items).toHaveLength(2);
  });

  it("renderRich returns the same blocks as renderBlocks", () => {
    const text = ["```js", "x();", "```"].join("\n");
    const { container } = render(<div>{renderRich(text)}</div>);
    expect(container.querySelector("code.rt__pre-code")?.textContent).toBe("x();");
  });
});
