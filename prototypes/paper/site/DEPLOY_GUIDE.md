# GitHub Pages 部署指南

## 第一步：创建 GitHub 仓库

1. 打开 https://github.com/new
2. Repository name 填: `tpe-paper` (或任何你喜欢的名字)
3. 选择 **Public**
4. 点 Create repository

## 第二步：上传文件

在你电脑的终端里执行：

```bash
cd prototypes/paper/site

git init
git add index.html
git commit -m "Add project page"
git branch -M main
git remote add origin https://github.com/你的用户名/tpe-paper.git
git push -u origin main
```

## 第三步：开启 GitHub Pages

1. 打开你的仓库页面: https://github.com/你的用户名/tpe-paper
2. 点 **Settings** (设置)
3. 左侧菜单找到 **Pages**
4. Source 选择 **Deploy from a branch**
5. Branch 选择 **main**, 文件夹选 **/ (root)**
6. 点 Save

## 第四步：访问你的网站

等 1-2 分钟后，你的网站就上线了：

```
https://你的用户名.github.io/tpe-paper/
```

## 后续更新

之后如果要更新页面，编辑 `index.html` 后：

```bash
git add index.html
git commit -m "Update page"
git push
```

GitHub Pages 会自动重新部署。

## 可选：绑定自定义域名

如果你有自己的域名，可以在 Settings → Pages → Custom domain 里填写。
