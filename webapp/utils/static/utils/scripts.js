var activeId = "#-1";
$(activeId).css("color", "red");

$(document).ready(function(){
    $("#add-dir-btn").click(function(){
        $("#focus").empty();
        var block = '<form method="POST" action="/add-dir/" style="overflow-x:hidden" style="overflow-x:hidden">{% csrf_token %}<div class="center"><label id="for_name">Name:<input id="for_name" type="text" maxlength="50" name="dir_name" required></label></div><div class="center"><label id="for_desc">Description:<input id="for_desc" type="text" maxlength="255" name="dir_desc"></label></div><br><div><label id="for_dest">Choose directory to create new directory in:<select name="dest_for_dir" id="dest_for_dir" style="width: 80%;" required><option value="-1">root</option>{% for dir in directories %}{% if dir.owner == user and dir.availability_flag == True %}<option value="{{ dir.id }}">{{ dir.name }}/</option>{% endif %}{% endfor %}</select></label></div><div class="center"><input type="submit" value="Submit"></div></form>';
        $("#focus").append(block);
    });
});

$(document).ready(function(){
    $("#add-file-btn").click(function(){
        $("#focus").empty();
        var block = '<div><form method="POST" action="/add-file/" enctype="multipart/form-data" style="overflow-x:hidden">{% csrf_token %}<div class="center"><label id="for_name">Name:<input id="for_name" type="text" maxlength="50" name="file_name" required></label></div><div class="center"><label id="for_desc">Description:<input id="for_desc" type="text" maxlength="255" name="file_desc"></label></div><div class="center"><label id="for_file">File:<input id="for_file" type="file" name="file_file" required></label></div><label id="for_dest">Choose directory to create new directory in:<select name="dest_for_file" id="dest_for_file" style="width: 80%;" required><option value="-1">root</option>{% for dir in directories %}{% if dir.owner == user and dir.availability_flag == True %}<option value="{{ dir.id }}">{{ dir.name }}/</option>{% endif %}{% endfor %}</select></label><div class="center"><input type="submit" value="Submit"></div></form></div>';
        $("#focus").append(block);
    });
});

$(document).ready(function(){
    $("#delete-btn").click(function(){
        $("#focus").empty();
        var block = '<form method="POST" action="/delete/">{% csrf_token %}<label id="for_file_or_dir">Choose file or directory:<br><select name="to_delete" id="to_delete" style="width: 80%;" required><option value="">Not chosen</option>{% for file in files %}{% if file.owner == user and file.availability_flag == True %}<option value="{{ file.id }}">{{ file.name }}</option>{% endif %}{% endfor %}{% for dir in directories %}{% if dir.owner == user and dir.availability_flag == True %}<option value="{{ dir.id }}">{{ dir.name }}/</option>{% endif %}{% endfor %}</select></label><br><input type="submit" value="Submit"></form>';
        $("#focus").append(block);
    });
});

$(document).ready(function(){
    $(".dir-listed").click(function(){
        $(activeId).css("color", "white");
        $(this).css("color", "red");
        activeId = "#" + $(this).attr("id");

        $(".textField").empty();
    });

    $(".file-listed").click(function(){
        $(activeId).css("color", "white");
        $(this).css("color", "red");
        activeId = "#" + $(this).attr("id");

        $(".textField").empty();
    });
});

function putInput(path, holdername) {
    console.log(path);
    if (path.length > 1 && holdername) {
        jQuery.get(path, function(txt) {
            $('.' + holdername).html("<pre class='preformatted'>" + txt + "</pre>");
        });
    }
}