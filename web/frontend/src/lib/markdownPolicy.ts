import type { Components } from 'react-markdown';

// Generated meeting text must not trigger image requests, including same-origin
// requests. Render only escaped alternate text; never pass through src/srcSet.
export const privateMarkdownComponents: Components = {
    img: ({ alt }) => alt ? `[Image omitted: ${alt}]` : null,
};
