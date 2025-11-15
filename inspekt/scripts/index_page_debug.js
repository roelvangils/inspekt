// Debug version to check image detection
(function() {
  const allImages = document.querySelectorAll('img');
  const imageInfo = [];

  allImages.forEach((img, idx) => {
    if (img.style.display === 'none' || img.style.visibility === 'hidden') return;

    const info = {
      index: idx,
      src: img.src,
      alt: img.alt || '(no alt)',
      naturalWidth: img.naturalWidth,
      naturalHeight: img.naturalHeight,
      width: img.width,
      height: img.height,
      complete: img.complete,
      classList: Array.from(img.classList).join(' ')
    };
    imageInfo.push(info);
  });

  return {
    totalImages: allImages.length,
    images: imageInfo
  };
})()
