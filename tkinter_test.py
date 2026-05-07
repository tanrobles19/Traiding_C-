import tkinter

window = tkinter.Tk()
window.title("Test OK")
window.geometry("400x200")

label = tkinter.Label(window, text="Hello!", font=("Arial", 20, "bold"))
label.pack()

window.mainloop()
