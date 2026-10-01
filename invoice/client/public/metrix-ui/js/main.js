$(document).ready(function () {

    // $('body').fadeTo('fast', 1);
    setMaskedIcons();
    $('.button_switch').click(function () {
        $(this).toggleClass('off');
    })

    $('body').on('click', '.toggle_handler', function (event) {
        event.stopPropagation();

        toggleHandler(this);
    });

    $('.toggle_handler').on('click', function (event) {
        event.stopPropagation();

        toggleHandler(this);
    });

    $('.toggle_content.auto_dismiss .select_item').click(function (e) {
        e.stopPropagation();

        const parent = $(this).parent('.toggle_content'),
            id = parent.attr('id');

        $('.toggle_handler[target-id="' + id + '"]').removeClass('opened');


        parent.hide();

    });

    $('.custom_scroll').on("scroll", function () {
        autoCloseToggleHandler();
    });

    $('.popup').prepend('<p class="overlay"></p>');

    $('.close_popup, .popup .overlay').click(function () {
        const id = $(this).parents('.popup').attr('id');

        closePopup(id);
    });

    $('.show_popup').click(function () {
        const id = $(this).attr('data-id');

        showPopup(id);
    });


    //Select2
    $('.input select').each(function () {

        const url = $(this).attr('data-url');
        var ajax = null;
        if (url != undefined) {
            ajax = {
                url: url,
                dataType: 'json',
                delay: 250,
                data: function (params) {
                    return {
                        term: params.term || '',
                        page: params.page || 1
                    }
                }
            };
        }

        var values = [];

        $(this).find('option').each(function () {
            const value = $(this).val();
            selected = $(this).attr('selected') == 'selected';

            if (selected) {
                values.push(value);
            }
        });

        $(this).select2({
            placeholder: $(this).attr('placeholder'),
            // minimumResultsForSearch: ($(this).attr('search') == undefined) ? Infinity : null,
            minimumResultsForSearch: -1,
            width: '100%',
            ajax: ajax,
        }).val(null).trigger('change');

        if ($(this).hasClass("bigger")) {
            $(this).next().addClass("bigger");
        }

        $(this).val(values).trigger('change');

    });


    $('.input_plus_minus .as_button').click(function () {
        const action = $(this).attr('data-id'),
            parent = $(this).parent('.input'),
            input = parent.find('input');

        var value = parseInt(input.val() || "0");

        action == 'plus' ? value++ : value--;

        if (value == 1) {
            value = 1;
            input.removeClass('centered');
            parent.find('.as_button[data-id="minus"]').hide();
        }
        else {
            input.addClass('centered');
            parent.find('.as_button[data-id="minus"]').show();
        }

        input.val(value);


    });



    //hidden_toggler
    $('.hidden_toggler .target').hide();
    $('.hidden_toggler .trigger').click(function () {
        $(this).hide();
        $(this).siblings('.target').slideDown('fast');
    });



    //side block
    $('#show_side_block').click(function () {
        $('#side_block').removeClass('hidden');
        $('#show_side_block').hide();
    })

    $('#hide_side_block').click(function () {
        $('#side_block').addClass('hidden');
        $('#show_side_block').show();
    });

    $('.sidebar_button').click(function () {
        $(this).toggleClass('active');
        $('.main').toggleClass('side_opened');
    });

});

function setMaskedIcons() {
    //ICONS
    $('.masked_icon:not(.initialized)').each(function () {
        $(this).addClass('initialized');
        let icon = $(this).attr('icon');

        $(this).css('mask-image', 'url(' + icon + ')');
        $(this).css('-webkit-mask-image', 'url(' + icon + ')');
    });
}


//TOGGLE HANDLER
function toggleHandler(item) {

    const id = $(item).attr('target-id'),
        parent = $(item).parents('.toggle_parent'),
        content = $('#' + id);

    if (content.hasClass('detach')) {
        $(document.body).append(content.detach());

        var top = $(item).offset().top + 54,
            left = $(item).offset().left

        if (top + content.height() > $(window).height()) {
            top = $(item).offset().top - content.height() - 16;
        }

        content.css({
            position: 'fixed',
            top: top,
            left: left,
        });
    }

    autoCloseToggleHandler(item);

    if ($(item).hasClass('opened')) {
        content.hide();
    }
    else {
        content.show();
    }

    $(item).toggleClass('opened');

    if ($(parent).length > 0) {
        const parentClass = $(parent).attr('toggle-class') || 'active';
        $(parent).toggleClass(parentClass);
    }
}


function autoCloseToggleHandler(exclusion = null) {
    $('.toggle_handler').each(function () {
        if (this != exclusion) {
            const id = $(this).attr('target-id'),
                content = $('#' + id);

            if (content.hasClass('auto_dismiss')) {
                content.hide();
                $(this).removeClass('opened');
            }
        }
    });
}

//POPUPS
function showPopup(id) {
    $('#' + id).fadeIn('fast');
}
function closePopup(id) {
    const popup = $('#' + id);
    if (!popup.hasClass('cant_close')) {
        popup.fadeOut('fast');
    }
}


//ALERTS
function showMessage(title, text, type = 'info') {
    var item = $(`<div class="alert ` + type + `">
            <span class="icon"></span>

            <div class="values">
                <p class="title">`+ title + `</p>
                <p class="value">`+ text + `</p>
            </div>
        </div>`);


    item.hide();

    var alerts = $('.alerts');
    if (alerts.length == 0) {
        alerts = $('body').append('<div class="alerts"></div>');
    }

    $('.alerts').append(item);
    item.fadeIn('fast');

    setTimeout(() => {
        item.slideUp('fast', function () {
            $(this).remove();
        });
    }, 2000);
}
