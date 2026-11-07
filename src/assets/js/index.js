let images = null

async function roll() {
    if(!images) {
        const response = await fetch("/assets/data/images.json");
        const json = await response.json();
        images = json;
    }
    const rand = Math.floor(Math.random()*images.length)
    const image = images[rand]
    document.querySelector("#cover-img").setAttribute("src",image.url)
    document.querySelector("#cover-img-title").setHTMLUnsafe(image.title ?? image.alt)
    document.querySelector("#cover-img-read-more-link").setAttribute("href",image.page_url)
}


roll();
document.querySelector("#roll").addEventListener("click", roll);

