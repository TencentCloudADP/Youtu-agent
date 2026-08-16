import React, { useMemo, useState, memo, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import type { Components } from 'react-markdown';
import remarkMath from 'remark-math';
import remarkGfm from 'remark-gfm';
import rehypeKatex from 'rehype-katex';
import rehypeRaw from 'rehype-raw';
import Mermaid from './Mermaid';
import BrokenImagePlaceholder from './BrokenImagePlaceholder';

// type CodeProps = React.DetailedHTMLProps<React.HTMLAttributes<HTMLElement>, HTMLElement> & {
//   inline?: boolean;
//   className?: string;
//   children?: React.ReactNode;
// };

interface MarkdownContentPart {
  type: "text" | "mermaid";
  content: string;
  inCompleteMermaid?: boolean;
}

// Memoized image component to prevent re-renders
const ImageWithErrorHandling = memo(({ src, alt, ...props }: { src?: string; alt?: string; [key: string]: any }) => {
  const [hasError, setHasError] = useState(false);
  
  if (hasError || !src) {
    return <BrokenImagePlaceholder src={src || ''} alt={alt} />;
  }
  
  return (
    <img 
      src={src}
      alt={alt}
      onError={() => setHasError(true)}
      style={{ maxWidth: '100%' }}
      {...props}
    />
  );
});

ImageWithErrorHandling.displayName = 'ImageWithErrorHandling';

// SafeMarkdown component with error boundary and type checking
const SafeMarkdown: React.FC<{ children: React.ReactNode, messageId: String }> = memo(({ children, messageId }) => {
  // const [mermaidCount, setMermaidCount] = useState(0);
  const [markdownParts, setMarkdownParts] = useState<Array<MarkdownContentPart>>([]);
  
  // Function to decode Unicode escape sequences like \u975ePDF
  const decodeUnicodeEscapes = (str: string): string => {
    return str.replace(/\\u([\dA-Fa-f]{4})/g, (_, hex) => {
      return String.fromCharCode(parseInt(hex, 16));
    });
  };

  const removeMermaidStartDelimiter = (content: string) => {
    return content.replace(/```mermaid/g, '');
  };

  const removeMermaidEndDelimiter = (content: string) => {
    return content.replace(/```/g, '');
  };

  // Convert children to string and decode Unicode escapes.
  // Strip stylesheet payloads so agent-generated HTML cannot restyle the app shell
  // (full HTML reports are isolated via iframe in MessageComponent).
  const content = useMemo(() => {
    const str = typeof children === 'string' ? children : String(children);
    return decodeUnicodeEscapes(str)
      .replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, '')
      .replace(/<link\b[^>]*\brel\s*=\s*["']?stylesheet["']?[^>]*>/gi, '');
  }, [children]);

  useEffect(() => {
    // Return early if content is empty
    if (!content.trim()) {
      return;
    }

    let splitedContentParts: Array<MarkdownContentPart> = [];
    let mermaidPattern = /^```mermaid\s*?\n([\s\S]*?)\n```$/gm;
    let inCompleteMermaidPattern = /^```mermaid\s*?\n([\s\S]*?)\z/gm;

    let mermaidMatches = content.matchAll(mermaidPattern);

    if (mermaidMatches) {
      let contentStartIndex = 0;
      let matchArr = Array.from(mermaidMatches);
      for (let i = 0; i < matchArr.length; i++) {
        let match = matchArr[i];
        let mermaidContent = match[0];
        let mermaidStartIndex = match.index;
        let mermaidEndIndex = mermaidStartIndex + mermaidContent.length;

        mermaidContent = removeMermaidStartDelimiter(mermaidContent);
        mermaidContent = removeMermaidEndDelimiter(mermaidContent);

        if (contentStartIndex < mermaidStartIndex) {
          let contentBeforeMermaid = content.substring(contentStartIndex, mermaidStartIndex);
          splitedContentParts.push({type: "text", content: contentBeforeMermaid});
        }
        
        splitedContentParts.push({type: "mermaid", content: mermaidContent});
        contentStartIndex = mermaidEndIndex;
      }
      if (contentStartIndex < content.length) {
        let contentAfterMermaid = content.substring(contentStartIndex, content.length);
        
        let inCompleteMermaidMatches = content.matchAll(inCompleteMermaidPattern);
        // at most one match
        let inCompleteMermaidMatch = inCompleteMermaidMatches.next().value;

        let realContentBeforeFinalMermaid = contentAfterMermaid;
        
        if (inCompleteMermaidMatch) {
          let inCompleteMermaidContent = inCompleteMermaidMatch[0];
          let inCompleteMermaidStartIndex = inCompleteMermaidMatch.index;
          realContentBeforeFinalMermaid = contentAfterMermaid.substring(0, inCompleteMermaidStartIndex);
          splitedContentParts.push({type: "text", content: realContentBeforeFinalMermaid});
          splitedContentParts.push({type: "mermaid", content: inCompleteMermaidContent, inCompleteMermaid: true});
        } else {
          splitedContentParts.push({type: "text", content: realContentBeforeFinalMermaid});
        }
      }
    } else {
      splitedContentParts.push({type: "text", content: content});
    }

    setMarkdownParts(splitedContentParts);
  }, [children]);

  try {
    const components: Components = {
      // Use memoized image component
      img: ImageWithErrorHandling,
      // Custom heading component to avoid conflicts with Mermaid
      h1: ({node, ...props}) => <h1 className="markdown-h1" {...props} />,
      h2: ({node, ...props}) => <h2 className="markdown-h2" {...props} />,
      h3: ({node, ...props}) => <h3 className="markdown-h3" {...props} />,
      // Agent-generated HTML often includes <style>/<link rel="stylesheet">.
      // With rehypeRaw these would inject into the app document and pollute the UI.
      // Drop them here; full HTML reports are rendered in a sandboxed iframe instead.
      style: () => null,
      link: ({ rel, ...props }) => {
        const relValue = typeof rel === 'string' ? rel.toLowerCase() : '';
        if (relValue.split(/\s+/).includes('stylesheet')) {
          return null;
        }
        return <link rel={rel} {...props} />;
      },
    };

    // const DebouncedMermaid = memo(({ chart, mermaidId }: { chart: string, mermaidId: string }) => {
    //   const [isVisible, setIsVisible] = useState(false);

    //   useEffect(() => {
    //     const timer = setTimeout(() => setIsVisible(true), 200);
    //     return () => clearTimeout(timer);
    //   }, []);

    //   return isVisible ? <Mermaid chart={chart} mermaidId={mermaidId} /> : <BrokenImagePlaceholder src={chart} alt="Mermaid Chart" />;
    // });

    return (
      <div className="markdown-content">
        {markdownParts.map((part, index) => {
          if (part.type === "text") {
            return <ReactMarkdown
              key={index}
              remarkPlugins={[remarkMath, remarkGfm]}
              rehypePlugins={[rehypeRaw, rehypeKatex]}
              components={components}
              skipHtml={false}
            >
              {part.content}
            </ReactMarkdown>;
          } else if (part.type === "mermaid") {
            if (part.inCompleteMermaid) {
              return <BrokenImagePlaceholder key={index} src="" alt="Mermaid Chart" />;
            } else {
              return <Mermaid key={index} chart={part.content} mermaidId={messageId + "-mermaid" + "-" + index} />;
            }
          }
        })}
      </div>
    );
  } catch (error) {
    console.error('Error rendering markdown:', error);
    // Fallback to plain text rendering if markdown parsing fails
    return <div className="plain-text">{String(children)}</div>;
  }
});

SafeMarkdown.displayName = 'SafeMarkdown';

export default SafeMarkdown;
