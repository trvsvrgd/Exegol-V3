def confirm_overwrite(filename):
    response = input(f"File '{filename}' already exists. Overwrite? (y/n) ")
    return response.lower() == 'y'