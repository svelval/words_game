let lang_selector = document.getElementById('lang_selector');
lang_selector.addEventListener('change', function () {
    let selected_lang_code = lang_selector.options[lang_selector.selectedIndex].id
    document.cookie = `lang=${selected_lang_code}`
    location.reload()
})
//
// lang_selector.onfocus = function () {
//     this.size = 4;
// }
// lang_selector.onblur = function () {
//     this.size = 0;
// }
// lang_selector.onchange = function () {
//     this.size = 1;
//     this.blur()
// }