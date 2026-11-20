// Whole-number presentation without changing untouched stored quantities.
window.KitchenNumbers=(()=>{
  const formatter=new Intl.NumberFormat('en-US',{maximumFractionDigits:0});
  const whole=value=>value==null||value===''?'':String(Math.round(Number(value)));
  const bind=(input,value)=>{
    input.value=whole(value);
    input.dataset.originalNumber=value==null?'':String(value);
    input.dataset.numberEdited='false';
    if(!input.dataset.wholeNumberBound){
      input.dataset.wholeNumberBound='true';
      input.addEventListener('input',()=>{input.dataset.numberEdited='true';});
      input.addEventListener('blur',()=>{
        if(input.value!==''&&Number.isFinite(Number(input.value)))input.value=whole(input.value);
      });
    }
  };
  const read=input=>input.dataset.numberEdited==='false'?input.dataset.originalNumber:whole(input.value);
  return Object.freeze({bind,read,format:value=>formatter.format(value)});
})();
