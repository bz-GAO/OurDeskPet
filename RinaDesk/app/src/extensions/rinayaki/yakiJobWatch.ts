/** Jobs created in the board stay visible to the pet after settings closes. */
const KEY='rinadesk:rinayaki:watched-jobs';

export function watchedYakiJobs():string[]{
 try{const values=JSON.parse(localStorage.getItem(KEY)||'[]');return Array.isArray(values)?values.filter((item):item is string=>typeof item==='string'&&item.length<4096).slice(-20):[];}
 catch{return [];}
}
export function watchYakiJob(job:string){
 const values=watchedYakiJobs().filter(item=>item!==job);
 localStorage.setItem(KEY,JSON.stringify([...values,job].slice(-20)));
}
export function forgetYakiJob(job:string){
 localStorage.setItem(KEY,JSON.stringify(watchedYakiJobs().filter(item=>item!==job)));
}
