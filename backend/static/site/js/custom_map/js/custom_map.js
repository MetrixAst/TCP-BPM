(function( $ ) {
    var mapTemplate = `
        <div id="map"></div>
            
        <div class="controls">
            <span class="zoom_in">+</span>
            <span class="zoom_out">-</span>
        </div>

        <div class="controls floors"></div>
	`;


    $.fn.myMap = $.fn.customMap = function(options) {
        var settings = $.extend({
			floors : 1,
            iconSize: 20,
            floorsStartFrom: 0,
            floorsPath: 'assets/img/floors',
            defaultIcon: '/assets/img/icon.png',
            currentFloor: 1,
            dataUrl: 'data.json',
			onTapped: null,
            onReady: null,
            floorLoaded: null,
        }, options );


        var svg = null,
            root = null,
            data = null,
            zoom = null;

        var mapContainer = this;
        mapContainer.addClass('map_container');
        mapContainer.html(mapTemplate);

        for (let current = settings.floors; current > settings.floorsStartFrom - 1; current--) {
            mapContainer.find('.floors').append('<span data-floor="'+current+'">'+current+'</span>');
        }

        fetch(settings.dataUrl)
        .then((response) => response.json())
        .then((json) => {

            mapContainer.addClass('loaded');
            data = json;

            mapContainer.find('.floors span').click(function(){
                const floor = $(this).attr('data-floor');
                floorTapped(floor, settings.floorLoaded);
            });

            d3.select(".controls .zoom_in").on("click", () => zoomAction(true));
            d3.select(".controls .zoom_out").on("click", () => zoomAction(false));

            floorTapped(settings.currentFloor, settings.floorLoaded);

            if(settings.onReady){
                settings.onReady();
            }
        });

        function floorTapped(floor, onReady){
            settings.currentFloor = parseInt(floor);

            mapContainer.find('.floors span').removeClass('selected');
            mapContainer.find('.floors span[data-floor='+floor+']').addClass('selected');

            initMap(settings.floorsPath+'/floor_'+floor+'.svg', onReady);
        }


        function initMap(floor, onReady){

            $('#map').load(floor, function(e){

                $('#map svg').attr({
                    id: 'svg_map',
                    width: '100%',
                    height: '100%',
                });

                svg = d3.select("#svg_map");
                root = d3.select("#svg_map > g");

                zoom = d3.zoom().on("zoom", handleZoom).scaleExtent([0.6, 7]);
                svg.call(zoom).on("dblclick.zoom", () => zoomAction(true));

                svg.selectAll('#objects path').on("click", function(d) {
                    const id = d3.select(this).attr('id');
                    objectSelected(id);
                });

                addLabels();

                if(onReady){
                    onReady();
                }
            });

        }


        function objectSelected(id){
            try {
                const path = svg.select('#'+id);

                svg.selectAll('#objects path').classed('selected', false);
                path.classed('selected', true);

                svg.selectAll('.map_label').classed('selected', false);
                svg.select('#label_'+id).classed('selected', true);

                // data.find()
                if(settings.onTapped != null){
                    const selectedObject = data.find((element) => element.map_id == id);

                    settings.onTapped({
                        map_id: id,
                        object: selectedObject || null,
                    });
                }
            } catch (err) {
                console.log(err);
                console.log("ID NOT FOUND");
            }
            
        }


        function handleZoom(e) {
            zoomLevel = e.transform.k | 0;
            if(zoomLevel > 5){
                zoomLevel = 5;
            }
            $('#svg_map').attr('zoom', zoomLevel);

            root.attr("transform", e.transform);
        }

        function zoomAction(plus){
            zoom.scaleBy(svg.transition().duration(200), plus ? 1.4 : 0.6);
        }

        function addLabels(){
            const filtered = data.filter((current) => current.floor == settings.currentFloor);

            filtered.forEach(function(current){
                const path = svg.select('#'+current.map_id);
                
                if(!path.empty()){

                    addIcon(current.map_id, path, current.icon);
                    addTextLabel(current.map_id, path, current.title);

                    if(current.class){
                        path.attr('class', current.class);
                    }
                }
            });
        }

        function addTextLabel(id, path, text){

            var bbox = path.node().getBBox();
                root.append("text")
                .attr("id", 'label_'+id)
                .attr('class', 'map_label')
                .attr("x", bbox.x + bbox.width / 2)
                .attr("y", bbox.y + bbox.height / 2 + settings.iconSize - 10)
                .attr("text-anchor", "middle")
                .attr("dominant-baseline", "middle")
                .attr("fill", "#5A5A5A")
                .text(text);

        }


        function addIcon(id, path, icon){

            if(!icon){
                icon = settings.defaultIcon;
            }

            var bbox = path.node().getBBox();
            root.append("image")
                .attr('id', 'icon_'+id)
                .attr('class', 'map_icon')
                .attr("x", bbox.x + bbox.width / 2 - settings.iconSize / 2)
                .attr("y", bbox.y + bbox.height / 2 - settings.iconSize / 2 - 10)
                .attr("height", settings.iconSize+"px")
                .attr("width", settings.iconSize+"px")
                .attr("xlink:href", function(d) {return icon}
            );
        }

        this.selectMapObject = function(map_id) {
            objectSelected(map_id);
        }

        this.selectObject = function(id) {
            const selectedObject = data.find((element) => element.id == id);
            if(selectedObject.floor != settings.currentFloor ){
                floorTapped(selectedObject.floor, () => {
                    objectSelected(selectedObject.map_id);
                });
            }
            else{
                objectSelected(selectedObject.map_id);
            }
        }

        this.settings = settings;

        return mapContainer;

    };

}( jQuery ));