import {artPacks} from '../pet/art/artPacks';
import {useArtPack} from '../pet/art/useArtPack';
export function ArtPackSelect(){
  const art=useArtPack();
  return <label className="art-pack-select">人物外观 <select aria-label="人物外观" value={art.id} onChange={e=>art.select(e.target.value)}>
    {artPacks.map(pack=><option value={pack.id} key={pack.id}>{pack.label}</option>)}
  </select></label>;
}
