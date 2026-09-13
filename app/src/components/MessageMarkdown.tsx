import { CodeBlock } from './CodeBlock';
import { memo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";
import "./MessageMarkdown.css";

const remarkPlugins = [remarkGfm, remarkMath];
const rehypePlugins: NonNullable<Parameters<typeof ReactMarkdown>[0]["rehypePlugins"]> = [
  [rehypeKatex, { trust: false, strict: "ignore", throwOnError: false }],
];

export default memo(function MessageMarkdown({ content }: { content: string }) {
  return (
    <div className="message-markdown">
      <ReactMarkdown
        remarkPlugins={remarkPlugins}
        rehypePlugins={rehypePlugins}
        skipHtml
        components={{
          pre: CodeBlock,
          a: ({ href, children }) => <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>,
          img: ({ alt }) => <span className="markdown-image-label">[图片：{alt || "请使用图片附件查看"}]</span>,
          table: ({ children }) => <div className="markdown-table-scroll"><table>{children}</table></div>,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
});
