import {FileBlob,SpreadsheetFile} from '@oai/artifact-tool';
import fs from 'node:fs/promises';
const w=await SpreadsheetFile.importXlsx(await FileBlob.load('C:/Users/servi/Downloads/recipes_DB-Recipes_modificato.xlsx'));
const s=w.worksheets.getItem('DB-Recipes');
const range=s.getRange('B1:C3826'); const values=range.values;
let count=0;
for(const row of values) for(let j=0;j<2;j++) if(typeof row[j]==='string' && row[j].includes('-')){row[j]=row[j].slice(row[j].indexOf('-')+1);count++;}
range.values=values;
w.recalculate();
await fs.writeFile('C:/Users/servi/.codex/worktrees/32c1/RF One/outputs/trim-recipes/trimmed-values.json',JSON.stringify(s.getRange('B1:C3826').values));
console.log(JSON.stringify({changed:count}));
