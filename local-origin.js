/* Move before any account/approval work; preserve the browser's theme choice. */
(()=>{
 const url=new URL(location.href);
 if(url.hostname==='127.0.0.1'){
  try{const theme=localStorage.getItem('lens-theme');if(['system','light','dark'].includes(theme))url.searchParams.set('lens_theme',theme)}catch{}
  url.hostname='localhost';location.replace(url.href);
 }else if(url.hostname==='localhost'&&url.searchParams.has('lens_theme')){
  const theme=url.searchParams.get('lens_theme');
  try{if(['system','light','dark'].includes(theme))localStorage.setItem('lens-theme',theme)}catch{}
  url.searchParams.delete('lens_theme');history.replaceState(null,'',url.pathname+url.search+url.hash);
 }
})();
