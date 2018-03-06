jQuery(function ($) {
    
    if($("#market_data")){
        console.log('markets card activated');
        var marketHtml = $(this).find(".js-card").html();

        var market = Handlebars.compile(marketHtml);
    
        var updateMarketView = function(){
            
            $(".js-market").each(function(i){
                var $this = $(this);
                $.getJSON("/market/" + $this.data("epic") + ".json",function(data){
                    $this.html(market(data));
                    $("time.js-timeago").timeago();
                });

            });
            $("#market_data .js-sort>li").sort(sort_list).appendTo('#market_data .js-sort');
           
        }

        setInterval(updateMarketView,1000);
    }

    if($("#trade_data")){
        var updateTradeView = function(){
            $.get("/get-trades", function(data){
                $("#trade_data .js-trades").html(data);
            })
            
            
        }

        setInterval(updateTradeView,2000);
    }

    
    function sort_list(a, b) {
        var aV = parseFloat($(a).find(".js-sortby").text());
        var bV = parseFloat($(b).find(".js-sortby").text());
        return bV < aV ? 1 : -1;
    }


    Handlebars.registerHelper('profit_loss',function(trade){
        var col = (trade.profit_loss<0) ? "darkred" : "navy";

        return new Handlebars.SafeString('<span style="color:' + col + '">' + trade.profit_loss.toFixed(2) + "</span>");
    });

    Handlebars.registerHelper('epic', function() {
        return this.epic.split('.')[2];
      });
    Handlebars.registerHelper('spread', function() {
        return this.spread.toFixed(2);
      });
    Handlebars.registerHelper('current_rsi',function(){
        return this.current_rsi.toFixed(2);
    })

    Handlebars.registerHelper('prediction.score',function(){
        return this.prediction.score.toFixed(2);
    })
    Handlebars.registerHelper('prediction.price_prediction',function(){
        return this.prediction.price_prediction.toFixed(2);
    })

    Handlebars.registerHelper('trends',function(){
        var res = '<svg class="trends" height="50" width="100%" xmlns="http://www.w3.org/2000/svg">\
        <line x1="0" y1="25" x2="100%" y2="25" stroke-width="1" stroke="black"/>';
        res += '<text x="0" y="7" font-size="8">MAX' + this.trends['MAX'].toFixed(2) + '</text>';
        var max = parseFloat(this.trends["MAX"]);
        delete this.trends['MAX'];
        var i =0;
        
        for(var obj in this.trends){
            var y = parseFloat(this.trends[obj].toFixed(2));
            var yS = (Math.abs(y)/max)*25;
            yS = y>0 ? yS*-1 : yS*1;
            yS += 25;
            var pos = 2 + (7.5 * i);
            var col = y>0 ? "blue" : "red";
            res += '<line x1="'+ pos +'%" y1="50%" x2="' + pos + '%" y2="' + yS + '" stroke-width="3" stroke="' + col + '"/>';
            res += '<text x="' + pos +'%" y="50%" font-size="8">' + obj + '</text>';
            i++;
        }
        res +="</svg>";
        return new Handlebars.SafeString(res);
    })
    

});