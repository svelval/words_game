from quart import render_template


async def not_found(e):
    return await render_template('404.html')


async def obj_not_found(error):
    return await render_template('460.html', obj_name=error.obj_name, obj=error.obj)