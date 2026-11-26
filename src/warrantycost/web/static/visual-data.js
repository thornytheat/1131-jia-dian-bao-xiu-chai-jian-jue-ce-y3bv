function drawProjectChart(target, points) {
    const shelf = named('div',undefined,'warranty-heat');
    const scale = Math.max(1,...points.map(p=>Math.abs(p.value)));
    for(const entry of points) {
        const tile = named('div',undefined,'warranty-bin');
        tile.style.setProperty('--heat', `${12 + Math.abs(entry.value)/scale*76}%`);
        tile.append(named('strong',entry.value),named('span',entry.label));
        shelf.append(tile);
    }
    target.append(shelf);
}
