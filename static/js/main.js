(function(){
  document.querySelectorAll('.flash').forEach(function(el){setTimeout(function(){el.style.opacity='0';el.style.transform='translateY(-4px)';setTimeout(function(){el.remove()},220)},5000)});
  document.addEventListener('keydown',function(e){if(e.key==='Escape'){document.body.classList.remove('filters-open','menu-open','admin-menu-open')}});
  document.querySelectorAll('a[href^="#"]').forEach(function(a){a.addEventListener('click',function(){document.body.classList.remove('menu-open')})});
})();
