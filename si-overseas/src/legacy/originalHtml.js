function requireMatch(source, match, label) {
    if (!match?.[1]) {
        throw new Error(`Unable to extract ${label} from original HTML.`);
    }
    return match[1].trim();
}
export function extractStyleBlock(html) {
    return requireMatch(html, html.match(/<style\b[^>]*>([\s\S]*?)<\/style>/i), 'style block');
}
export function extractBodyMarkup(html) {
    const body = requireMatch(html, html.match(/<body\b[^>]*>([\s\S]*?)<\/body>/i), 'body markup');
    const scriptStart = body.search(/<script\b/i);
    return (scriptStart === -1 ? body : body.slice(0, scriptStart)).trim();
}
export function extractInlineScript(html) {
    const scripts = [...html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi)]
        .map(match => match[1].trim())
        .filter(Boolean);
    if (!scripts.length) {
        throw new Error('Unable to extract inline script from original HTML.');
    }
    return scripts.join('\n\n');
}
