export type RinaTheme='paper'|'rose';
export const RINA_THEME_KEY='rinadesk.theme';

function valid(value:unknown):value is RinaTheme{return value==='paper'||value==='rose';}
export function currentTheme():RinaTheme{
  try{const value=localStorage.getItem(RINA_THEME_KEY);return valid(value)?value:'paper';}catch{return 'paper';}
}
export function applyTheme(theme:RinaTheme){
  document.documentElement.dataset.rinaTheme=theme;
}
export function selectTheme(theme:RinaTheme){
  try{localStorage.setItem(RINA_THEME_KEY,theme);}catch(error){console.warn('Theme preference could not be saved',error);}
  applyTheme(theme);window.dispatchEvent(new CustomEvent('rinadesk-theme-change',{detail:theme}));
}
export function initializeTheme(){
  applyTheme(currentTheme());
  window.addEventListener('storage',event=>{if(event.key===RINA_THEME_KEY)applyTheme(currentTheme());});
}
