(limit) => {
  const text = (x) => String(x || '').trim().slice(0, 500);
  const label = (e) => text(Array.from(e.labels || []).map(x => x.innerText).join(' '));
  const name = (e) => text(e.getAttribute('aria-label') ||
    (e.getAttribute('aria-labelledby') || '').split(/\s+/).map(id => document.getElementById(id)?.textContent || '').join(' ').trim() ||
    label(e) || (['BUTTON','A'].includes(e.tagName) ? e.innerText : '') ||
    (['submit','button','reset'].includes(e.type) ? e.value : '') || e.getAttribute('title'));
  const role = (e) => e.getAttribute('role') || ({BUTTON:'button',A:'link',TEXTAREA:'textbox',SELECT:e.multiple?'listbox':'combobox'}[e.tagName]) ||
    ({checkbox:'checkbox',radio:'radio',submit:'button',button:'button',range:'slider',number:'spinbutton'}[e.type]) || (e.tagName === 'INPUT' ? 'textbox' : '');
  const css = (e) => {
    const parts = [];
    for (let n=e; n && n.nodeType === 1 && parts.length < 6; n=n.parentElement) {
      if (n.id) { parts.unshift('#' + CSS.escape(n.id)); break; }
      const siblings = n.parentElement ? Array.from(n.parentElement.children).filter(x => x.tagName === n.tagName) : [];
      parts.unshift(n.tagName.toLowerCase() + (siblings.length > 1 ? ':nth-of-type(' + (siblings.indexOf(n)+1) + ')' : ''));
    }
    return parts.join(' > ');
  };
  const info = (e) => ({tag:e.tagName.toLowerCase(), role:role(e), accessible_name:name(e),
    text:text(e.tagName === 'BUTTON' || e.getAttribute('role') === 'button' ? e.innerText : ''),
    element_id:text(e.id), input_type:text(e.getAttribute('type') || (e.tagName === 'INPUT' ? 'text' : '')),
    name:text(e.name), placeholder:text(e.getAttribute('placeholder')), label:label(e),
    required:!!e.required, disabled:!!e.disabled, checked:['checkbox','radio'].includes(e.type) ? !!e.checked : null,
    multiple:!!e.multiple, options:e.tagName === 'SELECT' ? Array.from(e.options).slice(0,100).map(x=>text(x.text)) : [],
    test_id:text(e.getAttribute('data-testid')), css:css(e)});
  const buttons = 'button,[role="button"],input[type="submit"],input[type="button"],input[type="reset"]';
  const inputs = 'input,select,textarea';
  const take = (root, query) => Array.from(root.querySelectorAll(query)).slice(0,limit);
  return {
    links:take(document,'a[href],area[href],[role="link"][href]').map(e => ({href:e.getAttribute('href'),text:text(e.innerText || e.getAttribute('aria-label'))})),
    buttons:take(document,buttons).map(info), inputs:take(document,inputs).map(info),
    forms:take(document,'form').slice(0,25).map((e,i)=>({identifier:text(e.id || e.name || 'form-'+i),
      action:e.getAttribute('action') || location.pathname, method:(e.getAttribute('method') || 'GET').toUpperCase(),
      controls:take(e,inputs).map(info), buttons:take(e,buttons).map(info)}))
  };
}
